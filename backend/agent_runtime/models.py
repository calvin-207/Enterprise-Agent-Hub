"""Authoritative run, step, event and reliable dispatch intent models."""
import uuid
from django.conf import settings
from django.db import models


class AgentRun(models.Model):
    class Status(models.TextChoices):
        QUEUED = "QUEUED", "待执行"
        RUNNING = "RUNNING", "执行中"
        SUCCEEDED = "SUCCEEDED", "成功"
        FAILED = "FAILED", "失败"
        CANCELLED = "CANCELLED", "已取消"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent = models.ForeignKey("agents.Agent", on_delete=models.PROTECT, related_name="runs")
    version = models.ForeignKey("agents.AgentVersion", on_delete=models.PROTECT, related_name="runs")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="agent_runs")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED, db_index=True)
    status_version = models.PositiveIntegerField(default=1)
    input = models.JSONField(default=dict)
    input_digest = models.CharField(max_length=64)
    version_snapshot = models.JSONField(default=dict)
    idempotency_key = models.CharField(max_length=120)
    lease_token = models.UUIDField(null=True, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    deadline_at = models.DateTimeField(null=True, blank=True)
    result = models.JSONField(null=True, blank=True)
    error_code = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=("requested_by", "idempotency_key"), name="eah_run_idempotency"),
        ]
        indexes = [
            models.Index(fields=("status", "lease_until"), name="eah_run_lease_idx"),
        ]


class RunStep(models.Model):
    run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name="steps")
    sequence = models.PositiveIntegerField()
    kind = models.CharField(max_length=32)
    status = models.CharField(max_length=16)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("sequence",)
        constraints = [
            models.UniqueConstraint(fields=("run", "sequence"), name="eah_unique_run_step"),
        ]


class RunEvent(models.Model):
    run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name="events")
    sequence = models.PositiveIntegerField()
    kind = models.CharField(max_length=48)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("sequence",)
        constraints = [
            models.UniqueConstraint(fields=("run", "sequence"), name="eah_unique_run_event"),
        ]


class DispatchOutbox(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "待派发"
        SENDING = "SENDING", "正在派发"
        SENT = "SENT", "已派发"

    run = models.OneToOneField(AgentRun, on_delete=models.CASCADE, related_name="outbox")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=80, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=("status", "next_attempt_at"), name="eah_outbox_due_idx"),
        ]
