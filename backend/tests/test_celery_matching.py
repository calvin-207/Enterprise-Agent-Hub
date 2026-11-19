"""环境与版本匹配机制：队列隔离、消息盖章、Worker 校验与计划归属。

覆盖三类串流/误消费场景：
1. 测试环境的任务流入正式环境（跨环境消息被拒绝）；
2. 代码更新后未重启的旧 Worker 消费新版本消息（版本戳不一致被拒绝）；
3. 共用数据库时其他环境的 Beat 误触发本环境计划（计划归属校验）。
"""
from unittest.mock import patch

import pytest
from django.test import override_settings
from django_celery_beat.models import PeriodicTask

from automation.models import TaskDefinition, TaskExecution, TaskSchedule
from automation.scheduling import sync_schedule
from automation.tasks import execute_automation, trigger_schedule
from main.celery import message_origin_mismatch, stamp_message_headers
from main.settings import _normalize_env_tag
from system.tasks import ping


# ---------------- settings 推导 ----------------

def test_env_tag_normalization():
    assert _normalize_env_tag("Prod") == "prod"
    assert _normalize_env_tag("Feature X!") == "feature-x"
    assert _normalize_env_tag("  ci_2026 ") == "ci-2026"
    assert _normalize_env_tag("---") == ""
    assert len(_normalize_env_tag("a" * 100)) == 30


def test_default_queue_carries_env_tag():
    from django.conf import settings
    assert settings.CELERY_TASK_DEFAULT_QUEUE == f"hub-{settings.CELERY_ENV_TAG}"


# ---------------- 消息盖章 ----------------

@override_settings(CELERY_ENV_TAG="dev", HUB_CODE_VERSION="v1")
def test_stamp_message_headers_adds_env_and_version():
    headers = {}
    stamp_message_headers(headers=headers)
    assert headers == {"hub-env": "dev", "hub-version": "v1"}


@override_settings(CELERY_ENV_TAG="dev", HUB_CODE_VERSION="v1")
def test_stamp_message_headers_does_not_overwrite_explicit_values():
    headers = {"hub-env": "prod", "hub-version": "v9"}
    stamp_message_headers(headers=headers)
    assert headers == {"hub-env": "prod", "hub-version": "v9"}


# ---------------- Worker 侧校验 ----------------

@override_settings(CELERY_ENV_TAG="dev", HUB_CODE_VERSION="v1")
def test_mismatch_detection_matrix():
    assert message_origin_mismatch(None) is None            # 未盖章的历史/本地消息放行
    assert message_origin_mismatch({}) is None
    assert message_origin_mismatch({"hub-env": "dev", "hub-version": "v1"}) is None

    kind, reason = message_origin_mismatch({"hub-env": "prod", "hub-version": "v1"})
    assert kind == "env" and "prod" in reason and "dev" in reason

    kind, reason = message_origin_mismatch({"hub-env": "dev", "hub-version": "v2"})
    assert kind == "version" and "v2" in reason and "v1" in reason


# ---------------- automation.execute 行为 ----------------

@pytest.fixture
def admin(django_user_model):
    return django_user_model.objects.create_superuser(
        username="matching-admin", password="StrongTestPassword!2026", name="Matching Admin",
    )


@pytest.fixture
def queued_execution(db, admin):
    return TaskExecution.objects.create(
        title="Worker 连通性检测", task_type=TaskExecution.TaskType.PING,
        celery_task_id="matching-test-1", created_by=admin,
    )


def _run_with_headers(task, headers, args):
    """以真实消息头执行任务：celery 的 eager apply 原生支持 headers 参数。"""
    task.apply(args=args, headers=headers, throw=True)


@pytest.mark.django_db
@override_settings(CELERY_ENV_TAG="dev", HUB_CODE_VERSION="v1")
def test_execute_rejects_foreign_env_message(queued_execution):
    _run_with_headers(execute_automation, {"hub-env": "prod", "hub-version": "v1"}, (queued_execution.pk,))
    queued_execution.refresh_from_db()
    assert queued_execution.status == TaskExecution.Status.FAILED
    assert "prod" in queued_execution.error_message and "dev" in queued_execution.error_message


@pytest.mark.django_db
@override_settings(CELERY_ENV_TAG="dev", HUB_CODE_VERSION="v1")
def test_execute_rejects_stale_worker_version(queued_execution):
    _run_with_headers(execute_automation, {"hub-env": "dev", "hub-version": "v0"}, (queued_execution.pk,))
    queued_execution.refresh_from_db()
    assert queued_execution.status == TaskExecution.Status.FAILED
    assert "v0" in queued_execution.error_message and "v1" in queued_execution.error_message


@pytest.mark.django_db
@override_settings(CELERY_ENV_TAG="dev", HUB_CODE_VERSION="v1")
def test_execute_accepts_matching_message(queued_execution):
    _run_with_headers(execute_automation, {"hub-env": "dev", "hub-version": "v1"}, (queued_execution.pk,))
    queued_execution.refresh_from_db()
    assert queued_execution.status == TaskExecution.Status.SUCCESS
    assert queued_execution.result["worker_env"] == "dev"
    assert queued_execution.result["worker_version"] == "v1"


# ---------------- automation.trigger_schedule 行为 ----------------

@pytest.fixture
def schedule(db, admin):
    definition = TaskDefinition.objects.create(
        title="匹配检测", task_type=TaskExecution.TaskType.PING, created_by=admin,
    )
    return TaskSchedule.objects.create(
        name="匹配计划", definition=definition, created_by=admin,
        environment="prod", enabled=True,
    )


@pytest.mark.django_db
@override_settings(CELERY_ENV_TAG="dev", HUB_CODE_VERSION="v1")
def test_trigger_skips_schedule_from_other_environment(schedule):
    with patch("automation.services.execute_automation.apply_async") as send:
        _run_with_headers(trigger_schedule, {"hub-env": "dev", "hub-version": "v1"}, (schedule.pk,))
    assert send.call_count == 0
    assert TaskExecution.objects.count() == 0
    schedule.refresh_from_db()
    assert schedule.last_triggered_at is None


@pytest.mark.django_db
@override_settings(CELERY_ENV_TAG="dev", HUB_CODE_VERSION="v1")
def test_trigger_rejects_message_from_foreign_beat(schedule):
    schedule.environment = "dev"
    schedule.save(update_fields=["environment"])
    with patch("automation.services.execute_automation.apply_async") as send:
        _run_with_headers(trigger_schedule, {"hub-env": "prod", "hub-version": "v1"}, (schedule.pk,))
    assert send.call_count == 0
    assert TaskExecution.objects.count() == 0


@pytest.mark.django_db
@override_settings(CELERY_ENV_TAG="dev", HUB_CODE_VERSION="v1")
def test_trigger_runs_own_environment_schedule(schedule, django_capture_on_commit_callbacks):
    schedule.environment = "dev"
    schedule.save(update_fields=["environment"])
    with patch("automation.services.execute_automation.apply_async") as send:
        with django_capture_on_commit_callbacks(execute=True):
            _run_with_headers(trigger_schedule, {"hub-env": "dev", "hub-version": "v1"}, (schedule.pk,))
    assert send.call_count == 1
    assert TaskExecution.objects.count() == 1


# ---------------- 计划同步落戳与队列跟随 ----------------

@pytest.mark.django_db
@override_settings(CELERY_ENV_TAG="staging")
def test_sync_schedule_pins_environment_and_follows_default_queue(db, admin):
    definition = TaskDefinition.objects.create(
        title="落戳检测", task_type=TaskExecution.TaskType.PING, created_by=admin,
    )
    schedule = TaskSchedule.objects.create(name="待落戳计划", definition=definition, created_by=admin)
    assert schedule.environment == ""

    periodic = sync_schedule(schedule)
    schedule.refresh_from_db()
    assert schedule.environment == "staging"
    # 队列留空（None 或 ""）= 跟随应用默认队列（hub-<环境标签>），
    # 由运行 Beat 的环境决定目标；django-celery-beat 会把空串规范成 None。
    assert not periodic.queue
    assert periodic.enabled is False  # schedule.enabled 默认 False


@pytest.mark.django_db
def test_sync_schedule_never_writes_hardcoded_queue(db, admin):
    """同步不会把写死的 "default" 队列写回 PeriodicTask（迁移已清空历史值）。"""
    definition = TaskDefinition.objects.create(
        title="迁移检测", task_type=TaskExecution.TaskType.PING, created_by=admin,
    )
    schedule = TaskSchedule.objects.create(name="迁移计划", definition=definition, created_by=admin)
    periodic = sync_schedule(schedule)
    from django.db.models import Q
    assert PeriodicTask.objects.filter(Q(pk=periodic.pk) & (Q(queue="") | Q(queue__isnull=True))).exists()


# ---------------- 内置任务 ----------------

@override_settings(CELERY_ENV_TAG="dev", HUB_CODE_VERSION="v1")
def test_ping_reports_env_and_version():
    result = ping.apply(throw=True).get()
    assert result["status"] == "ok"
    assert result["env"] == "dev"
    assert result["version"] == "v1"


@override_settings(CELERY_ENV_TAG="dev", HUB_CODE_VERSION="v1")
def test_ping_rejects_foreign_env_message():
    outcome = ping.apply(throw=False, headers={"hub-env": "prod", "hub-version": "v1"})
    assert outcome.failed()
