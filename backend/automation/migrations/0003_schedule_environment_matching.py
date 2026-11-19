"""Schedule environment pinning + clear the hardcoded legacy queue on PeriodicTask.

1. TaskSchedule.environment 记录计划归属的环境标签（历史数据留空，下次保存落戳）。
2. 旧版 sync_schedule 把 PeriodicTask.queue 写死为 "default"；多环境共用 Broker 时，
   这会把所有环境的调度都投进同一条队列。改为空字符串 = 跟随应用默认队列
   （hub-<环境标签>），由运行 Beat 的环境在发布时决定。
"""
from django.db import migrations, models
from django.db.models import Q


def clear_legacy_queue(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(
        Q(name__startswith="enterprise-agent-hub:automation:") & ~Q(queue="")
    ).update(queue="")


def restore_legacy_queue(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name__startswith="enterprise-agent-hub:automation:").update(queue="default")


class Migration(migrations.Migration):
    dependencies = [
        ("automation", "0002_task_definitions_and_schedules"),
    ]

    operations = [
        migrations.AddField(
            model_name="taskschedule",
            name="environment",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.RunPython(clear_legacy_queue, restore_legacy_queue),
    ]
