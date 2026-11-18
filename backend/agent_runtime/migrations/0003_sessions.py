import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("agent_runtime", "0002_usage_and_cancel"),
        ("agents", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="AgentSession",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(default="新会话", max_length=120)),
                ("archived", models.BooleanField(db_index=True, default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("agent", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sessions", to="agents.agent")),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="agent_sessions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-updated_at",)},
        ),
        migrations.AddField(
            model_name="agentrun",
            name="session",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="runs", to="agent_runtime.agentsession"),
        ),
        migrations.CreateModel(
            name="AgentMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("user", "用户"), ("assistant", "助手")], max_length=12)),
                ("content", models.TextField(max_length=12000)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="messages", to="agent_runtime.agentrun")),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="agent_runtime.agentsession")),
            ],
            options={"ordering": ("id",)},
        ),
        migrations.AddIndex(model_name="agentsession", index=models.Index(fields=("owner", "archived"), name="eah_session_owner_idx")),
        migrations.AddConstraint(model_name="agentmessage", constraint=models.UniqueConstraint(fields=("run", "role"), name="eah_run_unique_msg_role")),
    ]
