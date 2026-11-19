"""Small, safe built-in tasks that verify the automation infrastructure.

Business tasks should live in their owning Django app's tasks.py. Do not pass
secrets, model instances or large payloads through Celery messages.
"""
import logging

from celery import shared_task
from django.db import connection
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name="system.ping", ignore_result=False)
def ping():
    """Verify that a worker can execute a JSON-serializable task."""
    return {"status": "ok", "service": "enterprise-agent-hub", "timestamp": timezone.now().isoformat()}


@shared_task(name="system.check_database", ignore_result=True)
def check_database():
    """Optional scheduled DB connectivity probe; no business data is mutated."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        if cursor.fetchone()[0] != 1:
            raise RuntimeError("Database connectivity probe returned an unexpected value")
    logger.info("Celery scheduled database connectivity probe succeeded")


@shared_task(name="system.ops_heartbeat", ignore_result=True)
def ops_heartbeat():
    """运维管理心跳：由 Beat 每 60 秒调度、Worker 执行。

    每次执行向 Redis 写两类数据，供 /api/system/ops/overview/ 读取：
    - ops:beat_hb          证明 Beat 调度链路活着（Beat 触发 + Worker 消费）；
    - ops:worker_hb (hash) 执行主机 -> 时间戳，即该 Worker 的最近心跳。

    失败只记日志不上抛：心跳属于可观测性数据，不应污染错误队列。
    """
    import socket

    from django.conf import settings
    from system.views.ops import _cache_key, OPS_BEAT_KEY, OPS_WORKER_KEY

    try:
        from django_redis import get_redis_connection
    except Exception as exc:  # pragma: no cover - django-redis 属于固定依赖
        logger.warning("Ops heartbeat skipped: %s", exc)
        return

    try:
        conn = get_redis_connection("default")
        now = timezone.now().isoformat()
        # 与 Celery 默认 worker 节点名（celery@<hostname>）保持一致，
        # 便于概览接口把心跳与 inspect 实时探测到的 Worker 对上号
        worker_name = f"celery@{socket.gethostname()}"
        pipe = conn.pipeline()
        pipe.set(_cache_key(OPS_BEAT_KEY), now, ex=900)
        pipe.hset(_cache_key(OPS_WORKER_KEY), worker_name, now)
        pipe.expire(_cache_key(OPS_WORKER_KEY), 1800)
        pipe.execute()
    except Exception:
        logger.exception("Ops heartbeat failed to report to Redis")
