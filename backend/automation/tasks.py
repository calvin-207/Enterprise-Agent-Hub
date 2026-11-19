"""Allowlisted automation operations, executed by a separate Celery worker."""
import logging

from celery import shared_task
from django.conf import settings
from django.db import IntegrityError, connection
from django.utils import timezone

from automation.models import TaskExecution, TaskSchedule
from main.celery import message_origin_mismatch

logger = logging.getLogger(__name__)


@shared_task(name="automation.execute", bind=True, ignore_result=True)
def execute_automation(self, execution_id):
    # 环境与版本匹配：消息头由发布方盖章（main.celery.stamp_message_headers）。
    # 不匹配时留下可观测的失败记录（UI 支持一键重试），而不是静默吞掉消息。
    mismatch = message_origin_mismatch(getattr(self.request, "headers", None))
    if mismatch is not None:
        kind, reason = mismatch
        logger.error("Automation execution %s rejected (%s mismatch): %s", execution_id, kind, reason)
        TaskExecution.objects.filter(
            pk=execution_id, status=TaskExecution.Status.QUEUED
        ).update(
            status=TaskExecution.Status.FAILED,
            error_message=f"Worker 拒绝执行：{reason}",
            finished_at=timezone.now(),
        )
        return

    # Atomic state transition prevents duplicate deliveries from executing twice.
    claimed = TaskExecution.objects.filter(
        pk=execution_id, status=TaskExecution.Status.QUEUED
    ).update(status=TaskExecution.Status.RUNNING, started_at=timezone.now())
    if not claimed:
        return

    try:
        execution = TaskExecution.objects.get(pk=execution_id)
        if execution.task_type == TaskExecution.TaskType.PING:
            result = {
                "message": "Celery Worker 已连接", "checked_at": timezone.now().isoformat(),
                "worker_env": settings.CELERY_ENV_TAG, "worker_version": settings.HUB_CODE_VERSION,
            }
        elif execution.task_type == TaskExecution.TaskType.DATABASE:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                if cursor.fetchone()[0] != 1:
                    raise RuntimeError("Database connectivity check failed")
            result = {
                "message": "数据库连接正常", "checked_at": timezone.now().isoformat(),
                "worker_env": settings.CELERY_ENV_TAG, "worker_version": settings.HUB_CODE_VERSION,
            }
        else:
            raise ValueError("Unsupported automation operation")
        TaskExecution.objects.filter(pk=execution_id, status=TaskExecution.Status.RUNNING).update(
            status=TaskExecution.Status.SUCCESS,
            result=result,
            error_message="",
            finished_at=timezone.now(),
        )
    except Exception:
        logger.exception("Automation execution %s failed", execution_id)
        TaskExecution.objects.filter(pk=execution_id, status=TaskExecution.Status.RUNNING).update(
            status=TaskExecution.Status.FAILED,
            error_message="任务执行失败，请查看 Worker 日志",
            finished_at=timezone.now(),
        )
        # No blind retry: business operations must implement idempotency first.


@shared_task(name="automation.trigger_schedule", bind=True, ignore_result=True)
def trigger_schedule(self, schedule_id):
    """Beat dispatches only this trusted task name with an integer schedule ID.

    The execution row carries a unique schedule/minute key. Duplicate Beat
    messages within a minute do not dispatch the business task twice.
    """
    if type(schedule_id) is not int or schedule_id <= 0:
        return

    # 环境与版本匹配：只执行由本环境、本版本 Beat 发布的调度消息。
    mismatch = message_origin_mismatch(getattr(self.request, "headers", None))
    if mismatch is not None:
        kind, reason = mismatch
        logger.error("Schedule %s trigger rejected (%s mismatch): %s", schedule_id, kind, reason)
        return

    schedule = TaskSchedule.objects.select_related(
        "definition", "created_by"
    ).filter(pk=schedule_id).first()
    if not schedule or not schedule.enabled or not schedule.definition.enabled:
        return
    # 计划归属校验：其他环境的 Beat（例如共用数据库的开发 Beat）即使把消息
    # 投到了本环境的队列，也不会触发不属于本环境的计划。
    if schedule.environment and schedule.environment != settings.CELERY_ENV_TAG:
        logger.warning(
            "Schedule %s belongs to environment %s; worker %s skipped it",
            schedule_id, schedule.environment, settings.CELERY_ENV_TAG,
        )
        return

    # Django currently uses USE_TZ=False and Asia/Shanghai as its clock.
    # A single Beat per deployment ensures minute alignment.
    slot = timezone.now().replace(second=0, microsecond=0)
    from automation.services import enqueue_execution

    try:
        enqueue_execution(
            task_type=schedule.definition.task_type,
            user=schedule.created_by,
            definition=schedule.definition,
            schedule=schedule,
            scheduled_slot=slot,
        )
    except IntegrityError:
        logger.info("Already enqueued schedule %s for minute %s", schedule_id, slot)
        return
    TaskSchedule.objects.filter(pk=schedule_id).update(last_triggered_at=timezone.now())
