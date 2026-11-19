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
    definition = models.ForeignKey("TaskDefinition", null=True, blank=True, on_delete=models.SET_NULL, related_name="executions")
    schedule = models.ForeignKey("TaskSchedule", null=True, blank=True, on_delete=models.SET_NULL, related_name="executions")
    scheduled_slot = models.DateTimeField(null=True, blank=True)
    result = models.JSONField(null=True, blank=True)
    error_message = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=["status", "-created_at"], name="automation_status_created_idx")]
        constraints = [models.UniqueConstraint(fields=["schedule", "scheduled_slot"], name="automation_unique_schedule_slot")]

    def __str__(self):
        return f"{self.title} ({self.status})"


class TaskDefinition(models.Model):
    """Admin-managed allowlisted task definition; never stores executable code."""
    title = models.CharField(max_length=120, unique=True)
    task_type = models.CharField(max_length=32, choices=TaskExecution.TaskType.choices)
    description = models.CharField(max_length=500, blank=True, default="")
    enabled = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="automation_definitions")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")

    def __str__(self):
        return self.title


class TaskSchedule(models.Model):
    """One database-backed Crontab for a reusable task definition."""
    name = models.CharField(max_length=120, unique=True)
    definition = models.ForeignKey(TaskDefinition, on_delete=models.CASCADE, related_name="schedules")
    # 计划归属的环境标签（settings.CELERY_ENV_TAG）。空值表示历史数据尚未归属，
    # 下次保存时由 sync_schedule 自动落戳；trigger_schedule 只执行本环境的计划，
    # 防止其他环境的 Beat 误触发（例如共用数据库的开发 Beat 触发生产计划）。
    environment = models.CharField(max_length=32, blank=True, default="")
    minute = models.CharField(max_length=60, default="0")
    hour = models.CharField(max_length=60, default="9")
    day_of_week = models.CharField(max_length=60, default="*")
    day_of_month = models.CharField(max_length=60, default="*")
    month_of_year = models.CharField(max_length=60, default="*")
    enabled = models.BooleanField(default=False)
    periodic_task = models.OneToOneField(
        "django_celery_beat.PeriodicTask", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="automation_schedule",
    )
    last_triggered_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="automation_schedules")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")

    def __str__(self):
        return self.name
