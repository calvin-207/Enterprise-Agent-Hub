from django.conf import settings
from django.db import models


class TaskExecution(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "排队中"
        RUNNING = "running", "执行中"
        SUCCESS = "success", "成功"
        FAILED = "failed", "失败"

    class TaskType(models.TextChoices):
        PING = "ping", "Worker 连通性检测"
        DATABASE = "database_probe", "数据库连通性检测"

    title = models.CharField(max_length=120)
    task_type = models.CharField(max_length=32, choices=TaskType.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED, db_index=True)
    celery_task_id = models.CharField(max_length=64, unique=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="automation_executions")
    retry_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="retry_executions")
    result = models.JSONField(null=True, blank=True)
    error_message = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=["status", "-created_at"], name="automation_status_created_idx")]

    def __str__(self):
        return f"{self.title} ({self.status})"
