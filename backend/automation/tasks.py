"""Allowlisted automation operations, executed by a separate Celery worker."""
import logging

from celery import shared_task
from django.db import connection
from django.utils import timezone

from automation.models import TaskExecution

logger = logging.getLogger(__name__)


@shared_task(name="automation.execute", bind=True, ignore_result=True)
def execute_automation(self, execution_id):
    # Atomic state transition prevents duplicate deliveries from executing twice.
    claimed = TaskExecution.objects.filter(
        pk=execution_id, status=TaskExecution.Status.QUEUED
    ).update(status=TaskExecution.Status.RUNNING, started_at=timezone.now())
    if not claimed:
        return

    try:
        execution = TaskExecution.objects.get(pk=execution_id)
        if execution.task_type == TaskExecution.TaskType.PING:
            result = {"message": "Celery Worker 已连接", "checked_at": timezone.now().isoformat()}
        elif execution.task_type == TaskExecution.TaskType.DATABASE:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                if cursor.fetchone()[0] != 1:
                    raise RuntimeError("Database connectivity check failed")
            result = {"message": "数据库连接正常", "checked_at": timezone.now().isoformat()}
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
