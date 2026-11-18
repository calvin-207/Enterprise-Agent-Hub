from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
        ("automation", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="TaskDefinition",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=120, unique=True)),
                ("task_type", models.CharField(choices=[("ping", "Worker 连通性检测"), ("database_probe", "数据库连通性检测")], max_length=32)),
                ("description", models.CharField(blank=True, default="", max_length=500)),
                ("enabled", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="automation_definitions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at", "-id")},
        ),
        migrations.CreateModel(
            name="TaskSchedule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True)),
                ("minute", models.CharField(default="0", max_length=60)),
                ("hour", models.CharField(default="9", max_length=60)),
                ("day_of_week", models.CharField(default="*", max_length=60)),
                ("day_of_month", models.CharField(default="*", max_length=60)),
                ("month_of_year", models.CharField(default="*", max_length=60)),
                ("enabled", models.BooleanField(default=False)),
                ("last_triggered_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="automation_schedules", to=settings.AUTH_USER_MODEL)),
                ("definition", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="schedules", to="automation.taskdefinition")),
                ("periodic_task", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="automation_schedule", to="django_celery_beat.periodictask")),
            ],
            options={"ordering": ("-created_at", "-id")},
        ),
        migrations.AddField(
            model_name="taskexecution",
            name="definition",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="executions", to="automation.taskdefinition"),
        ),
        migrations.AddField(
            model_name="taskexecution",
            name="schedule",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="executions", to="automation.taskschedule"),
        ),
        migrations.AddField(
            model_name="taskexecution",
            name="scheduled_slot",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="taskexecution",
            constraint=models.UniqueConstraint(fields=("schedule", "scheduled_slot"), name="automation_unique_schedule_slot"),
        ),
    ]
