from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TaskExecution",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=120)),
                ("task_type", models.CharField(choices=[("ping", "Worker 连通性检测"), ("database_probe", "数据库连通性检测")], max_length=32)),
                ("status", models.CharField(choices=[("queued", "排队中"), ("running", "执行中"), ("success", "成功"), ("failed", "失败")], db_index=True, default="queued", max_length=16)),
                ("celery_task_id", models.CharField(max_length=64, unique=True)),
                ("result", models.JSONField(blank=True, null=True)),
                ("error_message", models.CharField(blank=True, default="", max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="automation_executions", to=settings.AUTH_USER_MODEL)),
                ("retry_of", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="retry_executions", to="automation.taskexecution")),
            ],
            options={"ordering": ("-created_at", "-id")},
        ),
        migrations.AddIndex(
            model_name="taskexecution",
            index=models.Index(fields=["status", "-created_at"], name="automation_status_created_idx"),
        ),
    ]
