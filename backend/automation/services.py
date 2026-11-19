"""Creation and dispatch of allowlisted background jobs."""
import uuid

from django.db import transaction
from django.utils import timezone

from automation.models import TaskExecution
from automation.tasks import execute_automation

TASK_TITLES = {
    TaskExecution.TaskType.PING: "Worker 连通性检测",
    TaskExecution.TaskType.DATABASE: "数据库连通性检测",
}


def enqueue_execution(*, task_type, user, retry_of=None, definition=None, schedule=None, scheduled_slot=None):
    if task_type not in TASK_TITLES:
        raise ValueError("Unsupported task type")
    with transaction.atomic():
        execution = TaskExecution.objects.create(
            title=definition.title if definition is not None else TASK_TITLES[task_type],
            definition=definition,
            schedule=schedule,
            scheduled_slot=scheduled_slot,
            task_type=task_type,
            created_by=user,
            celery_task_id=str(uuid.uuid4()),
            retry_of=retry_of,
        )

        def dispatch():
            try:
                # 不指定 queue：跟随 settings.CELERY_TASK_DEFAULT_QUEUE（hub-<环境标签>），
                # 与 Worker 的消费队列自动匹配，测试任务不会流入正式环境队列。
                execute_automation.apply_async(
                    args=[execution.pk],
                    task_id=execution.celery_task_id,
                )
            except Exception:
                # Never log a broker URL/password in the API response.
                TaskExecution.objects.filter(
                    pk=execution.pk, status=TaskExecution.Status.QUEUED
                ).update(
                    status=TaskExecution.Status.FAILED,
                    error_message="任务投递失败，请检查 Redis / Worker 配置",
                    finished_at=timezone.now(),
                )

        transaction.on_commit(dispatch)
    return execution
