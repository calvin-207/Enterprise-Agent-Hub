# -*- coding: utf-8 -*-

"""
@Remark: 运维管理 —— 平台运行状态概览

为前端「运维管理」看板提供一揽子健康数据：
- 主机资源：CPU / 内存 / 磁盘（psutil）
- 数据库：连通性、延迟、版本（Django connection）
- Redis：连通性、延迟、内存占用、客户端数（django-redis 原生连接）
- Celery Worker：在线数量、并发、最近心跳（inspect 实时探测 + 定时心跳任务上报）
- Celery Beat：调度心跳是否新鲜（由 system.ops_heartbeat 定时任务上报）

设计约束：
- 任一组件探测失败只把该卡片标记为 error，接口本身绝不 5xx；
- 阈值统一收敛在本文件顶部，前端只负责展示。
"""

import os
import platform
import socket
import time
from datetime import datetime, timedelta

import django
from django.conf import settings
from django.db import connection
from django.utils import timezone
from rest_framework.permissions import IsAdminUser
from rest_framework.views import APIView
from utils.jsonResponse import DetailResponse

try:
    import psutil
except ImportError:  # 依赖未安装时仍然返回结构完整的响应，由卡片提示补装
    psutil = None

# ---------------- 阈值配置（百分比/毫秒） ----------------
CPU_WARN, CPU_ERROR = 75, 90
MEM_WARN, MEM_ERROR = 80, 90
DISK_WARN, DISK_ERROR = 80, 90
DB_LATENCY_WARN_MS, DB_LATENCY_ERROR_MS = 100, 500
REDIS_LATENCY_WARN_MS, REDIS_LATENCY_ERROR_MS = 50, 200
# 心跳新鲜度：Beat 调度间隔 60s，超过 3 个周期未上报视为异常
HEARTBEAT_FRESH_SECONDS = 180
HEARTBEAT_STALE_SECONDS = 900
INSPECT_TIMEOUT_SECONDS = 1.0

OPS_BEAT_KEY = "ops:beat_hb"
OPS_WORKER_KEY = "ops:worker_hb"


def _judge_percent(percent, warn, error):
    """按百分比阈值评定状态"""
    if percent is None:
        return "error"
    if percent >= error:
        return "error"
    if percent >= warn:
        return "warn"
    return "ok"


def _human_bytes(size):
    """字节数转人类可读文本"""
    if size is None:
        return "未知"
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"


def _cache_key(name):
    """心跳键沿用 Django Redis 缓存的 KEY_PREFIX，避免污染缓存库键空间"""
    prefix = settings.CACHES.get("default", {}).get("KEY_PREFIX", "")
    return f"{prefix}:{name}" if prefix else name


def _redis_conn():
    from django_redis import get_redis_connection

    return get_redis_connection("default")


def _decode(value):
    """redis 客户端未开启 decode_responses 时统一转字符串"""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _parse_iso(value):
    try:
        return datetime.fromisoformat(str(_decode(value)))
    except (TypeError, ValueError):
        return None


def check_cpu():
    if psutil is None:
        return {
            "key": "cpu",
            "title": "CPU",
            "status": "error",
            "message": "服务端未安装 psutil（pip install psutil）",
            "metrics": [],
        }
    percent = psutil.cpu_percent(interval=0.1)
    try:
        load1, load5, load15 = psutil.getloadavg()
        load_text = f"{load1:.2f} / {load5:.2f} / {load15:.2f}"
    except (NotImplementedError, OSError):
        load_text = "当前平台不可用"
    status = _judge_percent(percent, CPU_WARN, CPU_ERROR)
    message = {
        "ok": f"使用率 {percent:.0f}%",
        "warn": f"使用率偏高（{percent:.0f}%）",
        "error": f"使用率过高（{percent:.0f}%）",
    }[status]
    return {
        "key": "cpu",
        "title": "CPU",
        "status": status,
        "message": message,
        "percent": round(percent, 1),
        "metrics": [
            {"label": "逻辑核心", "value": str(psutil.cpu_count(logical=True) or "未知")},
            {"label": "系统负载 (1/5/15min)", "value": load_text},
        ],
    }


def check_memory():
    if psutil is None:
        return {
            "key": "memory",
            "title": "内存",
            "status": "error",
            "message": "服务端未安装 psutil（pip install psutil）",
            "metrics": [],
        }
    vm = psutil.virtual_memory()
    status = _judge_percent(vm.percent, MEM_WARN, MEM_ERROR)
    message = {
        "ok": f"已使用 {vm.percent:.0f}%",
        "warn": f"内存偏紧（{vm.percent:.0f}%），关注泄漏或扩容",
        "error": f"内存告急（{vm.percent:.0f}%），随时可能触发 OOM",
    }[status]
    return {
        "key": "memory",
        "title": "内存",
        "status": status,
        "message": message,
        "percent": round(vm.percent, 1),
        "metrics": [
            {"label": "已用 / 总量", "value": f"{_human_bytes(vm.used)} / {_human_bytes(vm.total)}"},
            {"label": "可用", "value": _human_bytes(vm.available)},
        ],
    }


def check_disk():
    if psutil is None:
        return {
            "key": "disk",
            "title": "磁盘",
            "status": "error",
            "message": "服务端未安装 psutil（pip install psutil）",
            "metrics": [],
        }
    target = str(settings.BASE_DIR)
    usage = psutil.disk_usage(target)
    status = _judge_percent(usage.percent, DISK_WARN, DISK_ERROR)
    message = {
        "ok": f"已使用 {usage.percent:.0f}%",
        "warn": f"空间偏高（{usage.percent:.0f}%），请规划清理",
        "error": f"空间不足（{usage.percent:.0f}%），日志/上传文件可能写满磁盘",
    }[status]
    return {
        "key": "disk",
        "title": "磁盘",
        "status": status,
        "message": message,
        "percent": round(usage.percent, 1),
        "metrics": [
            {"label": "已用 / 总量", "value": f"{_human_bytes(usage.used)} / {_human_bytes(usage.total)}"},
            {"label": "剩余可用", "value": _human_bytes(usage.free)},
            {"label": "监测路径", "value": target},
        ],
    }


def check_database():
    db_setting = settings.DATABASES["default"]
    engine = db_setting["ENGINE"].rsplit(".", 1)[-1]
    engine_label = {"sqlite3": "SQLite", "mysql": "MySQL", "postgresql": "PostgreSQL"}.get(
        engine, engine
    )
    if engine == "sqlite3":
        server = os.path.basename(db_setting.get("NAME", "db.sqlite3"))
    else:
        server = f"{db_setting.get('HOST', '?')}:{db_setting.get('PORT', '?')}/{db_setting.get('NAME', '?')}"
    version = "未知"
    start = time.perf_counter()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
            if connection.vendor == "sqlite":
                cursor.execute("SELECT sqlite_version()")
            elif connection.vendor == "mysql":
                cursor.execute("SELECT VERSION()")
            elif connection.vendor == "postgresql":
                cursor.execute("SHOW server_version")
            row = cursor.fetchone()
            if row:
                version = str(row[0])
        latency_ms = (time.perf_counter() - start) * 1000
    except Exception as exc:
        return {
            "key": "database",
            "title": "数据库",
            "status": "error",
            "message": f"连接失败：{exc}",
            "metrics": [{"label": "引擎", "value": engine_label}, {"label": "服务器", "value": server}],
        }
    if latency_ms >= DB_LATENCY_ERROR_MS:
        status, message = "error", f"响应过慢（{latency_ms:.0f}ms）"
    elif latency_ms >= DB_LATENCY_WARN_MS:
        status, message = "warn", f"响应偏慢（{latency_ms:.0f}ms）"
    elif connection.vendor == "sqlite" and not settings.DEBUG:
        status, message = "warn", "生产环境仍在使用 SQLite，建议切换 PostgreSQL/MySQL"
    else:
        status, message = "ok", "连接正常"
    return {
        "key": "database",
        "title": "数据库",
        "status": status,
        "message": message,
        "metrics": [
            {"label": "引擎", "value": engine_label},
            {"label": "服务器", "value": server},
            {"label": "版本", "value": version},
            {"label": "查询延迟", "value": f"{latency_ms:.1f} ms"},
        ],
    }


def check_redis():
    try:
        conn = _redis_conn()
    except Exception as exc:
        return {
            "key": "redis",
            "title": "Redis 缓存",
            "status": "error",
            "message": f"无法建立连接：{exc}",
            "metrics": [],
        }
    try:
        start = time.perf_counter()
        pong = conn.ping()
        latency_ms = (time.perf_counter() - start) * 1000
        if not pong:
            raise RuntimeError("PING 未返回 PONG")
        info = conn.info()
        dbsize = conn.dbsize()
    except Exception as exc:
        return {
            "key": "redis",
            "title": "Redis 缓存",
            "status": "error",
            "message": f"指令执行失败：{exc}",
            "metrics": [],
        }
    if latency_ms >= REDIS_LATENCY_ERROR_MS:
        status, message = "error", f"响应过慢（{latency_ms:.0f}ms）"
    elif latency_ms >= REDIS_LATENCY_WARN_MS:
        status, message = "warn", f"响应偏慢（{latency_ms:.0f}ms）"
    else:
        status, message = "ok", "连接正常"
    return {
        "key": "redis",
        "title": "Redis 缓存",
        "status": status,
        "message": message,
        "metrics": [
            {"label": "版本", "value": _decode(info.get("redis_version", "未知"))},
            {"label": "已用内存", "value": _decode(info.get("used_memory_human", "未知"))},
            {"label": "连接客户端", "value": str(info.get("connected_clients", "未知"))},
            {"label": "缓存键数量", "value": str(dbsize)},
            {"label": "PING 延迟", "value": f"{latency_ms:.1f} ms"},
        ],
    }


def _read_heartbeats():
    """读取心跳任务上报的 Beat / Worker 心跳数据；Redis 不可用时返回空结果"""
    beat_at, worker_hb = None, {}
    try:
        conn = _redis_conn()
        raw = conn.get(_cache_key(OPS_BEAT_KEY))
        if raw:
            beat_at = _parse_iso(raw)
        for field, value in conn.hgetall(_cache_key(OPS_WORKER_KEY)).items():
            parsed = _parse_iso(value)
            if not parsed:
                continue
            # 统一规范成完整 worker 名（celery@host，全小写），与 inspect 结果对齐；
            # 兼容历史数据里只存裸 hostname 的写法
            name = _decode(field).lower()
            if "@" not in name:
                name = f"celery@{name}"
            worker_hb[name] = parsed
    except Exception:
        pass
    return beat_at, worker_hb


def check_celery_worker(worker_hb):
    """实时 inspect 探测在线 Worker，并补充心跳任务上报的最近心跳时间"""
    from main.celery import app as celery_app

    try:
        inspector = celery_app.control.inspect(timeout=INSPECT_TIMEOUT_SECONDS)
        ping = inspector.ping() or {}
        stats = (inspector.stats() or {}) if ping else {}
    except Exception:
        ping, stats = {}, {}

    now = timezone.now()
    workers = []
    for name in sorted(ping):
        stat = stats.get(name) or {}
        pool = stat.get("pool") or {}
        hb_at = worker_hb.get(name.lower())
        workers.append(
            {
                "name": name,
                "alive": True,
                "concurrency": pool.get("max-concurrency"),
                "last_heartbeat": hb_at.strftime("%Y-%m-%d %H:%M:%S") if hb_at else None,
                "heartbeat_age": round((now - hb_at).total_seconds()) if hb_at else None,
            }
        )
    # 心跳里有、但实时探测未响应的主机：可能刚下线或正忙
    alive_lower = {name.lower() for name in ping}
    for host, hb_at in worker_hb.items():
        if host in alive_lower:
            continue
        workers.append(
            {
                "name": host,
                "alive": False,
                "concurrency": None,
                "last_heartbeat": hb_at.strftime("%Y-%m-%d %H:%M:%S"),
                "heartbeat_age": round((now - hb_at).total_seconds()),
            }
        )

    count = len(ping)
    concurrency_total = sum(
        w["concurrency"] or 0 for w in workers if w["alive"] and w["concurrency"]
    )
    if count == 0:
        status, message = "error", "未发现在线 Worker，异步任务将无法执行"
    elif count == 1 and concurrency_total in (0, 1):
        status = "warn" if settings.DEBUG else "error"
        message = (
            "仅 1 个单并发 Worker（--pool=solo）：任务执行期间会阻塞后续任务，"
            "生产环境建议增加并发"
        )
    else:
        status, message = "ok", f"{count} 个 Worker 在线"
    stale = [w for w in workers if w["alive"] and w["heartbeat_age"] is not None and w["heartbeat_age"] > HEARTBEAT_FRESH_SECONDS]
    if stale and status == "ok":
        status = "warn"
        message = f"{count} 个 Worker 在线，但 {len(stale)} 个心跳超时（可能长时间忙）"
    return {
        "key": "celery_worker",
        "title": "Celery Worker",
        "status": status,
        "message": message,
        "workers": workers,
        "metrics": [
            {"label": "在线数量", "value": str(count)},
            {"label": "总并发", "value": str(concurrency_total or "未知")},
        ],
    }


def check_celery_beat(beat_at):
    """Beat 本身不执行任务，通过 ops_heartbeat 定时任务的上报时间判断其存活"""
    scheduler = settings.CELERY_BEAT_SCHEDULER.rsplit(":", 1)[-1]
    schedule_enabled = bool(
        settings.CELERY_BEAT_SCHEDULE.get("system-ops-heartbeat")
    )
    if beat_at is None:
        if not schedule_enabled:
            status, message = "warn", "心跳调度未启用（CELERY_ENABLE_OPS_HEARTBEAT=false），无法监测 Beat"
        else:
            status, message = "warn", "尚未收到 Beat 心跳：Beat 可能未启动，或刚启动未满 1 个调度周期"
    else:
        age = (timezone.now() - beat_at).total_seconds()
        if age <= HEARTBEAT_FRESH_SECONDS:
            status, message = "ok", f"心跳正常（{age:.0f} 秒前）"
        elif age <= HEARTBEAT_STALE_SECONDS:
            status, message = "error", f"心跳已中断 {age:.0f} 秒，定时任务可能停止调度"
        else:
            status, message = "error", f"心跳丢失（最后上报于 {beat_at:%Y-%m-%d %H:%M:%S}）"
    return {
        "key": "celery_beat",
        "title": "Celery Beat",
        "status": status,
        "message": message,
        "metrics": [
            {"label": "调度器", "value": scheduler},
            {"label": "心跳间隔", "value": "60 秒（system.ops_heartbeat）" if schedule_enabled else "已停用"},
            {
                "label": "最近心跳",
                "value": beat_at.strftime("%Y-%m-%d %H:%M:%S") if beat_at else "未上报",
            },
        ],
    }


def _server_info():
    info = {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "django": django.get_version(),
        "time": timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if psutil is not None:
        proc = psutil.Process(os.getpid())
        uptime = timedelta(seconds=int(time.time() - proc.create_time()))
        info["process"] = {
            "pid": proc.pid,
            "uptime": str(uptime),
            "memory": _human_bytes(proc.memory_info().rss),
        }
    else:
        info["process"] = None
    return info


class OpsOverviewView(APIView):
    """
    get:
    运维管理 —— 平台运行状态概览（仅限管理端员工）
    """

    permission_classes = [IsAdminUser]

    def get(self, request):
        beat_at, worker_hb = _read_heartbeats()
        components = [
            check_cpu(),
            check_memory(),
            check_disk(),
            check_database(),
            check_redis(),
            check_celery_worker(worker_hb),
            check_celery_beat(beat_at),
        ]
        rank = {"ok": 0, "warn": 1, "error": 2}
        overall = max((c["status"] for c in components), key=lambda s: rank[s])
        counts = {level: sum(1 for c in components if c["status"] == level) for level in rank}
        risks = [
            f"{c['title']}：{c['message']}" for c in components if c["status"] != "ok"
        ]
        return DetailResponse(
            data={
                "server": _server_info(),
                "components": components,
                "overall": {
                    "status": overall,
                    "ok_count": counts["ok"],
                    "warn_count": counts["warn"],
                    "error_count": counts["error"],
                },
                "risks": risks,
                "thresholds": {
                    "cpu": {"warn": CPU_WARN, "error": CPU_ERROR},
                    "memory": {"warn": MEM_WARN, "error": MEM_ERROR},
                    "disk": {"warn": DISK_WARN, "error": DISK_ERROR},
                    "heartbeat_fresh_seconds": HEARTBEAT_FRESH_SECONDS,
                },
            },
            msg="获取成功",
        )
