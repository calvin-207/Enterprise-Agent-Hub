from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("agent_runtime", "0001_initial")]
    operations = [
        migrations.AlterField(
            "agentrun", "status",
            models.CharField(choices=[
                ("QUEUED", "待执行"), ("RUNNING", "执行中"), ("CANCEL_REQUESTED", "取消中"),
                ("SUCCEEDED", "成功"), ("FAILED", "失败"), ("CANCELLED", "已取消"),
            ], db_index=True, default="QUEUED", max_length=16),
        ),
        migrations.AlterField(
            "dispatchoutbox", "status",
            models.CharField(choices=[
                ("PENDING", "待派发"), ("SENDING", "正在派发"),
                ("SENT", "已派发"), ("CANCELLED", "已取消"),
            ], db_index=True, default="PENDING", max_length=12),
        ),
        migrations.CreateModel(
            name="ModelUsage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider_code", models.CharField(max_length=64)),
                ("model_code", models.CharField(max_length=120)),
                ("input_tokens", models.PositiveIntegerField(blank=True, null=True)),
                ("output_tokens", models.PositiveIntegerField(blank=True, null=True)),
                ("estimated_cost", models.DecimalField(blank=True, decimal_places=8, max_digits=16, null=True)),
                ("input_price_per_million", models.DecimalField(decimal_places=6, default=0, max_digits=14)),
                ("output_price_per_million", models.DecimalField(decimal_places=6, default=0, max_digits=14)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("run", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="model_usage", to="agent_runtime.agentrun")),
            ],
        ),
    ]
