"""V2: CRUD, Cron, safety, Beat synchronization, and scheduled run tests."""
from unittest.mock import patch

import pytest
from django_celery_beat.models import PeriodicTask
from rest_framework.test import APIClient

from automation.models import TaskDefinition, TaskExecution, TaskSchedule
from automation.scheduling import validate_cron
from automation.tasks import trigger_schedule


@pytest.fixture
def admin(django_user_model):
    return django_user_model.objects.create_superuser(
        username="scheduler-admin", password="StrongTestPassword!2026",
        name="Scheduler Admin",
    )


@pytest.fixture
def regular(django_user_model):
    return django_user_model.objects.create_user(
        username="scheduler-staff", password="StrongTestPassword!2026",
        name="Staff", is_staff=True,
    )


@pytest.fixture
def api(admin):
    client = APIClient()
    client.force_authenticate(user=admin)
    return client


@pytest.fixture
def definition(api):
    response = api.post(
        "/api/automation/definitions/",
        {"title": "定时健康检测", "task_type": "ping", "description": "Worker 状态", "enabled": True},
        format="json",
    )
    assert response.status_code == 201, response.data
    return TaskDefinition.objects.get(pk=response.data["data"]["id"])


@pytest.mark.django_db
def test_permissions_and_allowlist(admin, regular):
    client = APIClient()
    assert client.get("/api/automation/definitions/").status_code == 401
    assert client.get("/api/automation/schedules/").status_code == 401
    client.force_authenticate(user=regular)
    assert client.get("/api/automation/definitions/").status_code == 403
    assert client.get("/api/automation/schedules/").status_code == 403
    assert client.post("/api/automation/definitions/", {
        "title": "Unsafe", "task_type": "os.system"}, format="json").status_code == 403
    client.force_authenticate(user=admin)
    result = client.post("/api/automation/definitions/", {
        "title": "Unsafe", "task_type": "os.system"}, format="json")
    assert result.status_code == 400
    assert TaskDefinition.objects.count() == 0


@pytest.mark.django_db
def test_create_enable_disable_and_delete_plan(api, definition):
    url = "/api/automation/schedules/"
    response = api.post(url, {
        "name": "工作日九点检查", "definition": definition.pk,
        "minute": "0", "hour": "9", "day_of_week": "1-5",
        "day_of_month": "*", "month_of_year": "*", "enabled": True,
    }, format="json")
    assert response.status_code == 201, response.data
    schedule = TaskSchedule.objects.get(pk=response.data["data"]["id"])
    periodic = PeriodicTask.objects.get(pk=schedule.periodic_task_id)
    assert periodic.enabled is True
    assert periodic.task == "automation.trigger_schedule"
    assert periodic.args == f"[{schedule.pk}]"
    assert periodic.crontab.minute == "0"
    assert periodic.crontab.day_of_week == "1-5"
    assert len(api.get(url).data["data"]) == 1

    patch_result = api.patch(f"{url}{schedule.pk}/", {
        "minute": "*/15", "enabled": False,
    }, format="json")
    assert patch_result.status_code == 200, patch_result.data
    periodic.refresh_from_db()
    assert periodic.enabled is False
    assert periodic.crontab.minute == "*/15"

    assert api.patch(f"/api/automation/definitions/{definition.pk}/", {
        "enabled": False}, format="json").status_code == 200
    assert api.patch(f"{url}{schedule.pk}/", {"enabled": True}, format="json").status_code == 400
    periodic.refresh_from_db()
    assert not periodic.enabled

    assert api.delete(f"{url}{schedule.pk}/").status_code == 200
    assert not TaskSchedule.objects.filter(pk=schedule.pk).exists()
    assert not PeriodicTask.objects.filter(pk=periodic.pk).exists()


@pytest.mark.django_db
def test_invalid_cron_and_duplicate_name(api, definition):
    url = "/api/automation/schedules/"
    payload = {"name": "每小时", "definition": definition.pk, "minute": "0", "hour": "*"}
    assert api.post(url, {**payload, "minute": "60"}, format="json").status_code == 400
    assert api.post(url, {**payload, "day_of_month": "garbage"}, format="json").status_code == 400
    assert api.post(url, payload, format="json").status_code == 201
    assert api.post(url, payload, format="json").status_code == 400
    assert TaskSchedule.objects.count() == 1


@pytest.mark.django_db
def test_disabling_definition_pauses_beat_and_deleting_cleans_up(api, definition):
    response = api.post("/api/automation/schedules/", {
        "name": "每五分钟", "definition": definition.pk,
        "minute": "*/5", "hour": "*", "enabled": True,
    }, format="json")
    assert response.status_code == 201, response.data
    schedule = TaskSchedule.objects.get(pk=response.data["data"]["id"])
    periodic_id = schedule.periodic_task_id
    assert api.patch(f"/api/automation/definitions/{definition.pk}/", {"enabled": False}).status_code == 200
    assert PeriodicTask.objects.get(pk=periodic_id).enabled is False
    assert api.patch(f"/api/automation/definitions/{definition.pk}/", {"enabled": True}).status_code == 200
    assert PeriodicTask.objects.get(pk=periodic_id).enabled is True
    assert api.delete(f"/api/automation/definitions/{definition.pk}/").status_code == 200
    assert not TaskSchedule.objects.filter(pk=schedule.pk).exists()
    assert not PeriodicTask.objects.filter(pk=periodic_id).exists()


@pytest.mark.django_db
def test_duplicate_beat_trigger_only_creates_one_execution(api, definition, django_capture_on_commit_callbacks):
    response = api.post("/api/automation/schedules/", {
        "name": "一分钟一次", "definition": definition.pk,
        "minute": "*", "hour": "*", "enabled": True,
    }, format="json")
    assert response.status_code == 201
    plan = TaskSchedule.objects.get(pk=response.data["data"]["id"])

    with patch("automation.services.execute_automation.apply_async") as send:
        with django_capture_on_commit_callbacks(execute=True):
            trigger_schedule.apply(args=[plan.pk], throw=True)
            trigger_schedule.apply(args=[plan.pk], throw=True)
    assert TaskExecution.objects.filter(schedule=plan).count() == 1
    assert send.call_count == 1
    record = TaskExecution.objects.get(schedule=plan)
    assert record.scheduled_slot is not None
    assert record.definition_id == definition.pk

    response = api.post(f"/api/automation/schedules/{plan.pk}/run/")
    assert response.status_code == 202
    assert TaskExecution.objects.filter(schedule=plan).count() == 2


@pytest.mark.django_db
def test_missing_and_disabled_schedules_do_not_run(api, definition):
    from automation.models import TaskSchedule
    with patch("automation.services.execute_automation.apply_async") as send:
        trigger_schedule.apply(args=[99999], throw=True)
        assert send.call_count == 0
    response = api.post("/api/automation/schedules/", {
        "name": "禁用计划", "definition": definition.pk, "enabled": False,
    }, format="json")
    assert response.status_code == 201
    plan = TaskSchedule.objects.get(pk=response.data["data"]["id"])
    trigger_schedule.apply(args=[plan.pk], throw=True)
    assert TaskExecution.objects.count() == 0
