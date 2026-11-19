"""Celery application used by Django API, workers, and beat.

Worker and beat must be separate processes. Redis is configured in settings.py.

环境与版本匹配（防串环境 / 防旧版 Worker）：
- 发布方：before_task_publish 给每条消息盖 hub-env / hub-version 头；
- 消费方：任务入口调用 message_origin_mismatch 校验，不符则拒绝执行。
队列名由 settings.CELERY_TASK_DEFAULT_QUEUE（hub-<环境标签>）统一推导。
"""
import os

from celery import Celery
from celery.signals import before_task_publish

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")

app = Celery("enterprise_agent_hub")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@before_task_publish.connect
def stamp_message_headers(sender=None, headers=None, body=None, **kwargs):
    """给所有经由本应用发布的消息盖上环境与版本戳（幂等，可被外部显式指定覆盖）。"""
    if headers is None:
        return
    try:
        from django.conf import settings
        headers.setdefault("hub-env", settings.CELERY_ENV_TAG)
        headers.setdefault("hub-version", settings.HUB_CODE_VERSION)
    except Exception:  # pragma: no cover - 防御性：盖章失败不应阻断发布
        pass


def message_origin_mismatch(headers):
    """校验消息头与本 Worker 的环境 / 版本是否匹配。

    返回 None 表示放行（含未盖章的历史消息），否则返回 (类型, 中文说明)，
    类型为 "env"（跨环境串流，必须拒绝）或 "version"（旧/新版本 Worker，应标记失败）。
    """
    if not headers:
        return None
    from django.conf import settings
    msg_env = headers.get("hub-env")
    if msg_env and msg_env != settings.CELERY_ENV_TAG:
        return ("env", f"消息来自环境「{msg_env}」，当前 Worker 环境「{settings.CELERY_ENV_TAG}」")
    msg_version = headers.get("hub-version")
    if msg_version and msg_version != settings.HUB_CODE_VERSION:
        return ("version", f"消息版本「{msg_version}」与 Worker 版本「{settings.HUB_CODE_VERSION}」不一致，请重启 Worker")
    return None
