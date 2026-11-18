import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("model_gateway", "0001_initial"),
        ("tool_gateway", "0001_initial"),
    ]
    operations = [
        migrations.CreateModel(
            name="Agent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("code", models.SlugField(max_length=100, unique=True)),
                ("name", models.CharField(max_length=120)),
                ("description", models.CharField(blank=True, default="", max_length=500)),
                ("status", models.CharField(choices=[("draft", "草稿"), ("active", "已发布"), ("disabled", "已停用")], default="draft", max_length=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="owned_agents", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="AgentVersion",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("version_number", models.PositiveIntegerField()),
                ("status", models.CharField(choices=[("draft", "草稿"), ("published", "已发布")], default="draft", max_length=12)),
                ("system_prompt", models.TextField(max_length=20000)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("agent", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="versions", to="agents.agent")),
                ("model_profile", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="agent_versions", to="model_gateway.modelprofile")),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="authored_agent_versions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-version_number",)},
        ),
        migrations.CreateModel(
            name="AgentAccessGrant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("capability", models.CharField(choices=[("run", "运行"), ("manage", "管理")], max_length=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("agent", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="access_grants", to="agents.agent")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="agent_access_grants", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="ToolGrant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("enabled", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("version", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tool_grants", to="agents.agentversion")),
                ("tool", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="agent_grants", to="tool_gateway.tooldefinition")),
            ],
        ),
        migrations.AddConstraint(model_name="agentversion", constraint=models.UniqueConstraint(fields=("agent", "version_number"), name="eah_unique_agent_version")),
        migrations.AddConstraint(model_name="agentaccessgrant", constraint=models.UniqueConstraint(fields=("agent", "user", "capability"), name="eah_unique_agent_user_capability")),
        migrations.AddConstraint(model_name="toolgrant", constraint=models.UniqueConstraint(fields=("version", "tool"), name="eah_unique_version_tool")),
    ]
