from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from automation.models import TaskExecution
from automation.services import enqueue_execution
from automation.tasks import execute_automation


@pytest.fixture
def admin_user(django_user_model):
    return django_user_model.objects.create_superuser(
        username="automation-admin", password="StrongTestPassword!2026",
        name="Automation Admin",
    )


@pytest.fixture
def ordinary_user(django_user_model):
    return django_user_model.objects.create_user(
        username="automation-user", password="StrongTestPassword!2026",
        name="Ordinary User", is_staff=True,
    )


@pytest.mark.django_db
def test_only_superuser_can_list_and_launch(admin_user, ordinary_user, django_capture_on_commit_callbacks):
    client = APIClient()
    assert client.get("/api/automation/executions/").status_code == 401
    client.force_authenticate(user=ordinary_user)
    assert client.get("/api/automation/executions/").status_code == 403
    assert client.post("/api/automation/executions/", {"task_type": "ping"}, format="json").status_code == 403

    client.force_authenticate(user=admin_user)
    with patch("automation.services.execute_automation.apply_async") as dispatch:
        # Django test transaction defers on_commit callbacks until explicitly executed.
        with django_capture_on_commit_callbacks(execute=True):
            response = client.post("/api/automation/executions/", {"task_type": "ping"}, format="json")
        assert response.status_code == 202
        assert response.data["code"] == 2000
        assert TaskExecution.objects.count() == 1
        assert dispatch.call_count == 1
    assert client.get("/api/automation/executions/").data["data"]["total"] == 1
    assert client.post("/api/automation/executions/", {"task_type": "unknown"}, format="json").status_code == 400


@pytest.mark.django_db
def test_execution_is_idempotent_and_retry_requires_failure(admin_user, django_capture_on_commit_callbacks):
    with patch("automation.services.execute_automation.apply_async"):
        execution = enqueue_execution(task_type="ping", user=admin_user)
    execute_automation.apply(args=[execution.id], throw=True)
    execution.refresh_from_db()
    assert execution.status == TaskExecution.Status.SUCCESS
    assert execution.result["message"] == "Celery Worker 已连接"
    first_finished_at = execution.finished_at
    execute_automation.apply(args=[execution.id], throw=True)
    execution.refresh_from_db()
    assert execution.finished_at == first_finished_at

    client = APIClient()
    client.force_authenticate(user=admin_user)
    assert client.post(f"/api/automation/executions/{execution.id}/retry/").status_code == 400

    execution.status = TaskExecution.Status.FAILED
    execution.save(update_fields=["status"])
    with patch("automation.services.execute_automation.apply_async"):
        with django_capture_on_commit_callbacks(execute=True):
            result = client.post(f"/api/automation/executions/{execution.id}/retry/")
    assert result.status_code == 202
    assert TaskExecution.objects.filter(retry_of=execution).count() == 1


@pytest.mark.django_db
def test_broker_failure_is_recorded(admin_user, django_capture_on_commit_callbacks):
    with patch("automation.services.execute_automation.apply_async", side_effect=ConnectionError("broker")):
        with _commit_callbacks():
            execution = enqueue_execution(task_type="ping", user=admin_user)
    execution.refresh_from_db()
    assert execution.status == TaskExecution.Status.FAILED
    assert "投递失败" in execution.error_message


