"""Persist allowlisted Cron schedules to django-celery-beat.

Only our own PeriodicTask rows (namespaced by schedule ID) are touched.
Never expose PeriodicTask.task, args, kwargs, or queue to API clients.
"""
import json

from celery.schedules import crontab
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django_celery_beat.models import CrontabSchedule, PeriodicTask

CRON_FIELDS = ("minute", "hour", "day_of_week", "day_of_month", "month_of_year")
CRON_DEFAULTS = {
    "minute": "0", "hour": "9", "day_of_week": "*",
    "day_of_month": "*", "month_of_year": "*",
}


def validate_cron(data):
    """Validate all five Celery Cron expressions using Celery's own parser."""
    values = {key: str(data.get(key, CRON_DEFAULTS[key])).strip() for key in CRON_FIELDS}
    for key, value in values.items():
        if not value or len(value) > 60:
            raise ValidationError({key: "Cron 字段不能为空或超过 60 个字符"})
    try:
        crontab(**values)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValidationError({"cron": "无效的 Cron 表达式"}) from exc
    return values


def sync_schedule(schedule):
    """Update a single, fixed-task-name database schedule."""
    # 历史计划（environment 为空）在首次同步时落上当前环境标签。
    if not schedule.environment:
        schedule.environment = settings.CELERY_ENV_TAG
        type(schedule).objects.filter(pk=schedule.pk).update(environment=schedule.environment)
    cron, _ = CrontabSchedule.objects.get_or_create(
        timezone=settings.TIME_ZONE,
        **{key: getattr(schedule, key) for key in CRON_FIELDS},
    )
    name = f"enterprise-agent-hub:automation:{schedule.pk}"
    options = {
        "name": name,
        "task": "automation.trigger_schedule",
        "args": json.dumps([schedule.pk]),
        "kwargs": "{}",
        "crontab": cron,
        "interval": None,
        "solar": None,
        "clocked": None,
        "one_off": False,
        "enabled": bool(schedule.enabled and schedule.definition.enabled),
        # 留空 = 跟随应用默认队列 hub-<CELERY_ENV_TAG>：由运行 Beat 的环境
        # 在发布时决定目标队列，多环境共用 Broker 也不会互相串流。
        "queue": "",
    }
    if schedule.periodic_task_id:
        periodic = PeriodicTask.objects.filter(pk=schedule.periodic_task_id).first()
    else:
        periodic = None
    if periodic is None:
        periodic, _ = PeriodicTask.objects.update_or_create(
            name=name, defaults={key: value for key, value in options.items() if key != "name"}
        )
    else:
        for key, value in options.items():
            setattr(periodic, key, value)
        periodic.save()
    if schedule.periodic_task_id != periodic.pk:
        type(schedule).objects.filter(pk=schedule.pk).update(periodic_task=periodic)
        schedule.periodic_task = periodic
    return periodic


def delete_schedule(schedule):
    """Remove only its own Beat entry, then the application schedule."""
    with transaction.atomic():
        periodic_id = schedule.periodic_task_id
        schedule.delete()
        if periodic_id:
            PeriodicTask.objects.filter(pk=periodic_id).delete()
