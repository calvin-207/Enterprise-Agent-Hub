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

import json
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
from utils.jsonResponse import DetailResponse, ErrorResponse

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
# 主服务（API 进程）内存隐患阈值
MAIN_SERVICE_MEM_WARN_MB = 1024
MAIN_SERVICE_MEM_ERROR_MB = 2048

# 日志查看：目录、单次返回行数上限、单块读取大小
LOGS_DIR = os.path.join(settings.BASE_DIR, "logs")
LOG_DEFAULT_LINES = 200
LOG_MAX_LINES = 500
LOG_MAX_FILES = 30
# 实时尾随（tail -f）：轮询周期与单次增量上限（wsopslog 复用）
POLL_INTERVAL_SECONDS = 1.0
MAX_BATCH_LINES = 500
MAX_BATCH_BYTES = 262144  # 256KB

OPS_BEAT_KEY = "ops:beat_hb"
OPS_WORKER_KEY = "ops:worker_hb"
# Worker 心跳附带的环境/版本信息（JSON：{"env": ..., "version": ...}）
OPS_WORKER_META_KEY = "ops:worker_meta"
# 版本不匹配的 Beat 心跳被拒时留下的标记（JSON：beat/worker 两边版本 + 时间），
# 供 Beat 卡片区分「Beat 挂了」和「Beat 版本过旧被 Worker 拒绝」。
OPS_BEAT_MISMATCH_KEY = "ops:beat_mismatch"


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
    """心跳键沿用 Django Redis 缓存的 KEY_PREFIX，并叠加环境标签。

    多套环境共用同一个缓存 Redis 时，Beat / Worker 心跳按环境隔离，
    测试环境的心跳不会让正式环境的运维页面误判 Beat 存活。
    """
    prefix = settings.CACHES.get("default", {}).get("KEY_PREFIX", "")
    parts = [part for part in (prefix, settings.CELERY_ENV_TAG, name) if part]
    return ":".join(parts)


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


def check_main_service():
    """主服务（响应本接口的 Django/Daphne 进程）自身状态。

    接口能返回即证明进程活着；卡片重点暴露进程级隐患：
    内存持续增长（疑似泄漏）、进程 CPU 占用异常偏高。
    """
    title = "主服务（API）"
    if psutil is None:
        return {
            "key": "main_service",
            "title": title,
            "status": "warn",
            "message": "运行中（未安装 psutil，进程指标不可用）",
            "metrics": [
                {"label": "运行状态", "value": "运行中"},
                {"label": "框架", "value": f"Django {django.get_version()} · Python {platform.python_version()}"},
                {"label": "运行模式", "value": "开发模式（DEBUG）" if settings.DEBUG else "生产模式"},
            ],
        }
    try:
        proc = psutil.Process(os.getpid())
        rss_mb = proc.memory_info().rss / 1024 / 1024
        cpu_percent = proc.cpu_percent(interval=0.1)
        uptime_seconds = int(time.time() - proc.create_time())
        threads = proc.num_threads()
        uptime_text = str(timedelta(seconds=uptime_seconds))
    except (psutil.Error, OSError) as exc:
        return {
            "key": "main_service",
            "title": title,
            "status": "error",
            "message": f"进程指标读取失败：{exc}",
            "metrics": [],
        }
    if rss_mb >= MAIN_SERVICE_MEM_ERROR_MB:
        status, message = "error", f"内存占用过高（{rss_mb:.0f} MB），疑似泄漏，请重启或排查"
    elif rss_mb >= MAIN_SERVICE_MEM_WARN_MB:
        status, message = "warn", f"内存占用偏高（{rss_mb:.0f} MB），关注增长趋势"
    else:
        status, message = "ok", f"运行中，内存 {rss_mb:.0f} MB"
    return {
        "key": "main_service",
        "title": title,
        "status": status,
        "message": message,
        "metrics": [
            {"label": "运行状态", "value": "运行中（本接口可响应即为证明）"},
            {"label": "进程 PID", "value": str(proc.pid)},
            {"label": "已运行", "value": uptime_text},
            {"label": "进程内存", "value": f"{rss_mb:.0f} MB"},
            {"label": "进程 CPU", "value": f"{cpu_percent:.0f}%"},
            {"label": "线程数", "value": str(threads)},
            {"label": "框架", "value": f"Django {django.get_version()} · Python {platform.python_version()}"},
            {"label": "运行模式", "value": "开发模式（DEBUG）" if settings.DEBUG else "生产模式"},
        ],
    }


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
    beat_at, worker_hb, worker_meta, beat_mismatch = None, {}, {}, None
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
        for field, value in conn.hgetall(_cache_key(OPS_WORKER_META_KEY)).items():
            name = _decode(field).lower()
            if "@" not in name:
                name = f"celery@{name}"
            try:
                meta = json.loads(_decode(value))
                worker_meta[name] = {"env": meta.get("env"), "version": meta.get("version")}
            except (ValueError, TypeError, AttributeError):
                continue
        mismatch_raw = conn.get(_cache_key(OPS_BEAT_MISMATCH_KEY))
        if mismatch_raw:
            try:
                beat_mismatch = json.loads(_decode(mismatch_raw))
            except (ValueError, TypeError, AttributeError):
                beat_mismatch = None
    except Exception:
        pass
    return beat_at, worker_hb, worker_meta, beat_mismatch


def check_celery_worker(worker_hb, worker_meta=None):
    """实时 inspect 探测在线 Worker，并补充心跳任务上报的最近心跳时间"""
    from main.celery import app as celery_app

    worker_meta = worker_meta or {}
    try:
        inspector = celery_app.control.inspect(timeout=INSPECT_TIMEOUT_SECONDS)
        ping = inspector.ping() or {}
        stats = (inspector.stats() or {}) if ping else {}
    except Exception:
        ping, stats = {}, {}

    def _meta(name_lower):
        return worker_meta.get(name_lower) or {}

    now = timezone.now()
    workers = []
    for name in sorted(ping):
        stat = stats.get(name) or {}
        pool = stat.get("pool") or {}
        hb_at = worker_hb.get(name.lower())
        meta = _meta(name.lower())
        workers.append(
            {
                "name": name,
                "alive": True,
                "concurrency": pool.get("max-concurrency"),
                "last_heartbeat": hb_at.strftime("%Y-%m-%d %H:%M:%S") if hb_at else None,
                "heartbeat_age": round((now - hb_at).total_seconds()) if hb_at else None,
                "env": meta.get("env"),
                "version": meta.get("version"),
            }
        )
    # 心跳里有、但实时探测未响应的主机：可能刚下线或正忙
    alive_lower = {name.lower() for name in ping}
    for host, hb_at in worker_hb.items():
        if host in alive_lower:
            continue
        meta = _meta(host)
        workers.append(
            {
                "name": host,
                "alive": False,
                "concurrency": None,
                "last_heartbeat": hb_at.strftime("%Y-%m-%d %H:%M:%S"),
                "heartbeat_age": round((now - hb_at).total_seconds()),
                "env": meta.get("env"),
                "version": meta.get("version"),
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
    # 环境与版本匹配体检：上报了 meta 且与本服务不一致的 Worker 视为隐患。
    # （未上报的老版本 Worker 不强判，避免升级期间误报）
    mismatched = [
        w for w in workers if w["alive"] and w["env"] is not None
        and (w["env"] != settings.CELERY_ENV_TAG or w["version"] != settings.HUB_CODE_VERSION)
    ]
    if mismatched:
        foreign = [w for w in mismatched if w["env"] != settings.CELERY_ENV_TAG]
        detail = "存在与本服务环境/版本不一致的在线 Worker，任务可能被旧进程拒绝执行"
        if foreign:
            detail = (
                f"{len(foreign)} 个 Worker 属于其他环境（如测试），共用 Broker 时有串环境风险，"
                "请检查 HUB_ENV 配置"
            )
        if status == "ok":
            status = "warn"
        message = f"{message}；{detail}"
    return {
        "key": "celery_worker",
        "title": "Celery Worker",
        "status": status,
        "message": message,
        "workers": workers,
        "metrics": [
            {"label": "在线数量", "value": str(count)},
            {"label": "总并发", "value": str(concurrency_total or "未知")},
            {"label": "本服务环境", "value": settings.CELERY_ENV_TAG},
            {"label": "本服务版本", "value": settings.HUB_CODE_VERSION},
        ],
    }


def check_celery_beat(beat_at, beat_mismatch=None):
    """Beat 本身不执行任务，通过 ops_heartbeat 定时任务的上报时间判断其存活。

    版本不匹配的判定优先于心跳新鲜度：被拒的心跳会留下 ops:beat_mismatch 标记，
    此时 Beat 进程其实活着，但它的调度消息正被 Worker 逐条拒绝——
    必须显式报告「重启 Beat」，而不是笼统的「心跳丢失」。
    """
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

    metrics = [
        {"label": "调度器", "value": scheduler},
        {"label": "心跳间隔", "value": "60 秒（system.ops_heartbeat）" if schedule_enabled else "已停用"},
        {
            "label": "最近心跳",
            "value": beat_at.strftime("%Y-%m-%d %H:%M:%S") if beat_at else "未上报",
        },
    ]

    mismatch = _active_beat_mismatch(beat_mismatch)
    if mismatch:
        beat_version = mismatch.get("beat_version") or "未知"
        worker_version = mismatch.get("worker_version") or "未知"
        metrics.append({"label": "Beat 版本", "value": beat_version})
        metrics.append({"label": "Worker 版本", "value": worker_version})
        if status == "ok":
            # 心跳仍正常但出现过被拒消息：多个 Worker 版本混布，部分心跳被拒
            status = "warn"
            message = (
                f"心跳部分正常，但检测到版本不匹配的 Beat/Worker 组合"
                f"（beat={beat_version} / worker={worker_version}），请统一版本"
            )
        else:
            status = "error"
            message = (
                f"Beat 在运行但版本与 Worker 不一致（beat={beat_version} / worker={worker_version}），"
                "调度消息已被 Worker 拒绝，全部定时计划停摆，请立即重启 Beat"
            )

    return {
        "key": "celery_beat",
        "title": "Celery Beat",
        "status": status,
        "message": message,
        "metrics": metrics,
    }


def _active_beat_mismatch(beat_mismatch):
    """校验版本不匹配标记是否仍在刷新（旧 Beat 每 60 秒被拒一次会持续续期）"""
    if not beat_mismatch:
        return None
    reported_at = _parse_iso(beat_mismatch.get("ts"))
    if reported_at is None:
        return None
    if (timezone.now() - reported_at).total_seconds() > HEARTBEAT_FRESH_SECONDS:
        return None
    return beat_mismatch


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
        beat_at, worker_hb, worker_meta, beat_mismatch = _read_heartbeats()
        components = [
            check_main_service(),
            check_cpu(),
            check_memory(),
            check_disk(),
            check_database(),
            check_redis(),
            check_celery_worker(worker_hb, worker_meta),
            check_celery_beat(beat_at, beat_mismatch),
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


# ================================================= #
# ************** 系统日志查看（运维页 Tab） ************** #
# ================================================= #


def _decode_text(data):
    """日志文件解码：优先 utf-8，兼容中文 Windows 下进程输出可能用的 GBK"""
    for encoding in ("utf-8", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _list_log_files():
    """枚举 logs 目录下的 .log 文件（按修改时间倒序），轮转分卷(.log.N)不展示"""
    files = []
    try:
        names = os.listdir(LOGS_DIR)
    except OSError:
        return files
    for name in names:
        if not name.endswith(".log"):
            continue
        path = os.path.join(LOGS_DIR, name)
        if not os.path.isfile(path):
            continue
        try:
            stat = os.stat(path)
        except OSError:
            continue
        files.append(
            {
                "name": name,
                "size": stat.st_size,
                "size_text": _human_bytes(stat.st_size),
                "mtime": datetime.fromtimestamp(stat.st_mtime).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "_sort": stat.st_mtime,
            }
        )
    files.sort(key=lambda item: item["_sort"], reverse=True)
    for item in files:
        item.pop("_sort", None)
    return files[:LOG_MAX_FILES]


def _tail_lines(path, limit):
    """从文件尾部按块回读最后 limit 行；大文件（轮转上限 20MB）不全量读入内存"""
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            remaining = handle.tell()
            buf = b""
            while remaining > 0 and buf.count(b"\n") <= limit:
                step = min(8192, remaining)
                remaining -= step
                handle.seek(remaining)
                buf = handle.read(step) + buf
        lines = _decode_text(buf).splitlines()
        return lines[-limit:]
    except OSError:
        return []


class OpsLogsView(APIView):
    """
    get:
    运维管理 —— 系统日志查看（仅限管理端员工）

    无 file 参数：返回可查看的日志文件列表；
    file + lines：返回该文件末尾 N 行（1-500），关键字过滤由前端完成。
    文件名只允许精确匹配已枚举的日志文件，天然拒绝路径穿越。
    """

    permission_classes = [IsAdminUser]

    def get(self, request):
        files = _list_log_files()
        file_name = (request.query_params.get("file") or "").strip()
        if not file_name:
            return DetailResponse(data={"files": files}, msg="获取成功")

        matched = next((item for item in files if item["name"] == file_name), None)
        if matched is None:
            return ErrorResponse(msg="日志文件不存在或不可读", code=400)

        try:
            lines_limit = int(request.query_params.get("lines", LOG_DEFAULT_LINES))
        except (TypeError, ValueError):
            lines_limit = LOG_DEFAULT_LINES
        lines_limit = min(max(lines_limit, 1), LOG_MAX_LINES)

        lines = _tail_lines(os.path.join(LOGS_DIR, file_name), lines_limit)
        return DetailResponse(
            data={"file": matched, "lines": lines, "requested": lines_limit},
            msg="获取成功",
        )


# ================================================= #
# ************** Worker 节点详情（点击下钻） ************** #
# ================================================= #


def _format_active_task(task):
    """归一化 inspect.active 返回的单条任务，超长参数截断避免撑爆响应"""
    args = task.get("args")
    if isinstance(args, (list, tuple)):
        args = ", ".join(str(arg) for arg in args)
    args = str(args or "")
    time_start = task.get("time_start")
    if isinstance(time_start, (int, float)):
        time_start = datetime.fromtimestamp(time_start).strftime("%Y-%m-%d %H:%M:%S")
    return {
        "id": str(task.get("id") or "")[:36],
        "name": task.get("name") or "未知任务",
        "args": args[:200] + ("…" if len(args) > 200 else ""),
        "time_start": time_start,
        "worker_pid": task.get("worker_pid"),
        "acknowledged": task.get("acknowledged"),
    }


class OpsWorkerDetailView(APIView):
    """
    get:
    运维管理 —— 单个 Celery Worker 节点详情（仅限管理端员工）

    ?name=celery@host：定向 inspect 该节点的 stats/active/scheduled/reserved/registered，
    并叠加心跳上报的环境与版本信息；节点离线时返回 online=False 与最后心跳。
    """

    permission_classes = [IsAdminUser]

    def get(self, request):
        name = (request.query_params.get("name") or "").strip()
        if not name:
            return ErrorResponse(msg="缺少 name 参数", code=400)

        from main.celery import app as celery_app

        inspector = celery_app.control.inspect(
            timeout=INSPECT_TIMEOUT_SECONDS, destination=[name]
        )
        stats = active = scheduled = reserved = registered = None
        try:
            online = bool(inspector.ping())
            if online:
                stats = (inspector.stats() or {}).get(name)
                active = (inspector.active() or {}).get(name)
                scheduled = (inspector.scheduled() or {}).get(name)
                reserved = (inspector.reserved() or {}).get(name)
                registered = (inspector.registered() or {}).get(name)
        except Exception:
            online = False

        _, worker_hb, worker_meta, _ = _read_heartbeats()
        hb_at = worker_hb.get(name.lower())
        meta = worker_meta.get(name.lower()) or {}
        stats = stats or {}
        pool = stats.get("pool") or {}
        total = {k: v for k, v in (stats.get("total") or {}).items() if isinstance(v, (int, float))}

        return DetailResponse(
            data={
                "name": name,
                "online": online,
                "env": meta.get("env"),
                "version": meta.get("version"),
                "last_heartbeat": hb_at.strftime("%Y-%m-%d %H:%M:%S") if hb_at else None,
                "heartbeat_age": round((timezone.now() - hb_at).total_seconds()) if hb_at else None,
                "concurrency": pool.get("max-concurrency"),
                "processes": pool.get("processes"),
                "pid": stats.get("pid"),
                "uptime_seconds": stats.get("uptime"),
                "total_tasks": sum(total.values()),
                "top_tasks": sorted(total.items(), key=lambda kv: kv[1], reverse=True)[:8],
                "active": [_format_active_task(t) for t in (active or [])],
                "active_count": len(active or []),
                "scheduled_count": len(scheduled or []),
                "reserved_count": len(reserved or []),
                "registered_count": len(registered or []),
            },
            msg="获取成功",
        )
