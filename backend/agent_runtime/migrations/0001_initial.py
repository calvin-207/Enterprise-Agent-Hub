import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("agents", "0001_initial"),
    ]
    operations = [
        migrations.CreateModel(
            name="AgentRun",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(choices=[("QUEUED", "待执行"), ("RUNNING", "执行中"), ("SUCCEEDED", "成功"), ("FAILED", "失败"), ("CANCELLED", "已取消")], db_index=True, default="QUEUED", max_length=16)),
                ("status_version", models.PositiveIntegerField(default=1)),
                ("input", models.JSONField(default=dict)),
                ("input_digest", models.CharField(max_length=64)),
                ("version_snapshot", models.JSONField(default=dict)),
                ("idempotency_key", models.CharField(max_length=120)),
                ("lease_token", models.UUIDField(blank=True, null=True)),
                ("lease_until", models.DateTimeField(blank=True, null=True)),
                ("deadline_at", models.DateTimeField(blank=True, null=True)),
                ("result", models.JSONField(blank=True, null=True)),
                ("error_code", models.CharField(blank=True, default="", max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("agent", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="runs", to="agents.agent")),
                ("version", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="runs", to="agents.agentversion")),
                ("requested_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="agent_runs", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.CreateModel(
            name="RunEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sequence", models.PositiveIntegerField()),
                ("kind", models.CharField(max_length=48)),
                ("payload", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="agent_runtime.agentrun")),
            ],
            options={"ordering": ("sequence",)},
        ),
        migrations.CreateModel(
            name="RunStep",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sequence", models.PositiveIntegerField()),
                ("kind", models.CharField(max_length=32)),
                ("status", models.CharField(max_length=16)),
                ("details", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="steps", to="agent_runtime.agentrun")),
            ],
            options={"ordering": ("sequence",)},
        ),
        migrations.CreateModel(
            name="DispatchOutbox",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("PENDING", "待派发"), ("SENDING", "正在派发"), ("SENT", "已派发")], db_index=True, default="PENDING", max_length=12)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("next_attempt_at", models.DateTimeField(blank=True, null=True)),
                ("lease_until", models.DateTimeField(blank=True, null=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.CharField(blank=True, default="", max_length=80)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("run", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="outbox", to="agent_runtime.agentrun")),
            ],
        ),
        migrations.AddConstraint(model_name="agentrun", constraint=models.UniqueConstraint(fields=("requested_by", "idempotency_key"), name="eah_run_idempotency")),
        migrations.AddIndex(model_name="agentrun", index=models.Index(fields=("status", "lease_until"), name="eah_run_lease_idx")),
        migrations.AddConstraint(model_name="runevent", constraint=models.UniqueConstraint(fields=("run", "sequence"), name="eah_unique_run_event")),
        migrations.AddConstraint(model_name="runstep", constraint=models.UniqueConstraint(fields=("run", "sequence"), name="eah_unique_run_step")),
        migrations.AddIndex(model_name="dispatchoutbox", index=models.Index(fields=("status", "next_attempt_at"), name="eah_outbox_due_idx")),
    ]
