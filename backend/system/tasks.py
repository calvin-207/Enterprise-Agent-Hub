"""Small, safe built-in tasks that verify the automation infrastructure.

Business tasks should live in their owning Django app's tasks.py. Do not pass
secrets, model instances or large payloads through Celery messages.
"""
import json
import logging
import socket

from celery import shared_task
from django.conf import settings
from django.db import connection
from django.utils import timezone

from main.celery import message_origin_mismatch

logger = logging.getLogger(__name__)


def _origin_ok(request_headers):
    """非本环境/非本版本的消息直接跳过：内置任务只服务自己的部署。"""
    mismatch = message_origin_mismatch(request_headers)
    if mismatch is not None:
        kind, reason = mismatch
        logger.error("Built-in task skipped (%s mismatch): %s", kind, reason)
        return False
    return True


@shared_task(name="system.ping", bind=True, ignore_result=False)
def ping(self):
    """Verify that a worker can execute a JSON-serializable task."""
    mismatch = message_origin_mismatch(getattr(self.request, "headers", None))
    if mismatch is not None:
        kind, reason = mismatch
        raise RuntimeError(f"Worker 拒绝执行 ping：{reason}")
    return {
        "status": "ok",
        "service": "enterprise-agent-hub",
        "timestamp": timezone.now().isoformat(),
        # 返回执行方环境与版本，供 CI / 运维页面核对“消息与 Worker 是否同源”。
        "env": settings.CELERY_ENV_TAG,
        "version": settings.HUB_CODE_VERSION,
    }


@shared_task(name="system.check_database", bind=True, ignore_result=True)
def check_database(self):
    """Optional scheduled DB connectivity probe; no business data is mutated."""
    if not _origin_ok(getattr(self.request, "headers", None)):
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        if cursor.fetchone()[0] != 1:
            raise RuntimeError("Database connectivity probe returned an unexpected value")
    logger.info("Celery scheduled database connectivity probe succeeded")


@shared_task(name="system.ops_heartbeat", bind=True, ignore_result=True)
def ops_heartbeat(self):
    """运维管理心跳：由 Beat 每 60 秒调度、Worker 执行。

    每次执行向 Redis 写三类数据，供 /api/system/ops/overview/ 读取：
    - ops:beat_hb          证明 Beat 调度链路活着（Beat 触发 + Worker 消费）；
    - ops:worker_hb (hash) 执行主机 -> 时间戳，即该 Worker 的最近心跳；
    - ops:worker_meta(hash) 执行主机 -> {env, version}，用于识别串环境的 Worker。

    失败只记日志不上抛：心跳属于可观测性数据，不应污染错误队列。
    """
    try:
        from django_redis import get_redis_connection
    except Exception as exc:  # pragma: no cover - django-redis 属于固定依赖
        logger.warning("Ops heartbeat skipped: %s", exc)
        return

    if not _origin_ok(getattr(self.request, "headers", None)):
        # 心跳消息来自其他环境（共用 Broker 时可能发生）：不写入本环境的心跳数据，
        # 避免运维页面把别环境的 Beat/Worker 误判为本环境的存活信号。
        return

    try:
        from system.views.ops import OPS_BEAT_KEY, OPS_WORKER_KEY, OPS_WORKER_META_KEY, _cache_key
        conn = get_redis_connection("default")
        now = timezone.now().isoformat()
        # 与 Celery 默认 worker 节点名（celery@<hostname>）保持一致，
        # 便于概览接口把心跳与 inspect 实时探测到的 Worker 对上号
        worker_name = f"celery@{socket.gethostname().lower()}"
        meta = json.dumps({"env": settings.CELERY_ENV_TAG, "version": settings.HUB_CODE_VERSION, "ts": now})
        pipe = conn.pipeline()
        pipe.set(_cache_key(OPS_BEAT_KEY), now, ex=900)
        pipe.hset(_cache_key(OPS_WORKER_KEY), worker_name, now)
        pipe.expire(_cache_key(OPS_WORKER_KEY), 1800)
        pipe.hset(_cache_key(OPS_WORKER_META_KEY), worker_name, meta)
        pipe.expire(_cache_key(OPS_WORKER_META_KEY), 1800)
        pipe.execute()
    except Exception:
        logger.exception("Ops heartbeat failed to report to Redis")
