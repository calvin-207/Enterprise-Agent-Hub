"""运维管理概览接口测试

覆盖：
- 权限：未登录 401 / 非员工 403 / 管理端员工可访问
- 结构：7 个组件齐全、状态取值合法、overall 与 risks 统计一致
- 降级：Redis / Celery 不可用时组件标记 error，接口本身不 5xx
- 心跳任务：ops_heartbeat 通过 pipeline 写入 Beat 与 Worker 心跳键
"""
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.conf import settings
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from system.tasks import ops_heartbeat
from system.views.ops import _judge_percent, check_celery_beat

EXPECTED_COMPONENT_KEYS = [
    "cpu",
    "memory",
    "disk",
    "database",
    "redis",
    "celery_worker",
    "celery_beat",
]


# 平台约定：鉴权失败由 CustomExceptionHandler 统一转成 HTTP 200 + 业务码
# （未认证 code=4001，无权限 code=4000），因此这里断言业务码而不是 HTTP 状态。


@pytest.mark.django_db
def test_ops_overview_requires_authentication():
    client = APIClient()
    response = client.get("/api/system/ops/overview/")
    assert response.status_code == 200
    assert response.json()["code"] == 4001


@pytest.mark.django_db
def test_ops_overview_rejects_non_staff(normal_user):
    client = APIClient()
    client.force_authenticate(user=normal_user)
    response = client.get("/api/system/ops/overview/")
    assert response.status_code == 200
    assert response.json()["code"] == 4000


@pytest.mark.django_db
def test_ops_overview_returns_all_components_for_staff(admin_user):
    client = APIClient()
    client.force_authenticate(user=admin_user)
    response = client.get("/api/system/ops/overview/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 2000

    data = payload["data"]
    assert [c["key"] for c in data["components"]] == EXPECTED_COMPONENT_KEYS
    for component in data["components"]:
        assert component["status"] in {"ok", "warn", "error"}
        assert component["title"]
        assert component["message"]

    overall = data["overall"]
    assert (
        overall["ok_count"] + overall["warn_count"] + overall["error_count"]
        == len(EXPECTED_COMPONENT_KEYS)
    )
    non_ok = [c for c in data["components"] if c["status"] != "ok"]
    assert len(data["risks"]) == len(non_ok)
    assert data["server"]["hostname"]


@pytest.mark.django_db
def test_ops_overview_degrades_gracefully_when_infra_down(admin_user, monkeypatch):
    """Broker 完全不可达时接口仍返回 200，Worker/心跳组件进入 error/warn"""
    from main.celery import app as celery_app

    monkeypatch.setattr(
        celery_app.control,
        "inspect",
        MagicMock(side_effect=ConnectionError("broker unreachable")),
    )
    client = APIClient()
    client.force_authenticate(user=admin_user)
    response = client.get("/api/system/ops/overview/")
    assert response.status_code == 200
    components = response.json()["data"]["components"]
    by_key = {c["key"]: c for c in components}
    assert by_key["celery_worker"]["status"] == "error"
    assert "Worker" in by_key["celery_worker"]["message"]
    assert by_key["celery_beat"]["status"] in {"warn", "error"}


@pytest.mark.django_db
def test_ops_heartbeat_writes_beat_and_worker_keys(monkeypatch):
    pipe = MagicMock()
    conn = MagicMock()
    conn.pipeline.return_value = pipe
    monkeypatch.setattr("django_redis.get_redis_connection", lambda name: conn)

    ops_heartbeat()

    assert conn.pipeline.call_count == 1
    beat_key = pipe.set.call_args.args[0]
    assert beat_key.endswith("ops:beat_hb")
    assert pipe.set.call_args.kwargs.get("ex") == 900
    hset_keys = [call.args[0] for call in pipe.hset.call_args_list]
    assert any(key.endswith("ops:worker_hb") for key in hset_keys)
    # Worker 心跳同时上报环境/版本，供运维页面识别串环境的 Worker
    meta_calls = [call for call in pipe.hset.call_args_list if call.args[0].endswith("ops:worker_meta")]
    assert len(meta_calls) == 1
    assert "env" in meta_calls[0].args[2] and "version" in meta_calls[0].args[2]
    assert pipe.expire.called
    assert pipe.execute.called


@pytest.mark.django_db
def test_celery_beat_status_follows_heartbeat_freshness():
    assert check_celery_beat(timezone.now())["status"] == "ok"
    stale = check_celery_beat(timezone.now() - timedelta(seconds=400))
    assert stale["status"] == "error"
    missing = check_celery_beat(None)
    assert missing["status"] == "warn"
    assert "心跳" in missing["message"]


@pytest.mark.django_db
@override_settings(CELERY_ENV_TAG="dev", HUB_CODE_VERSION="v1")
def test_ops_heartbeat_version_mismatch_writes_marker(monkeypatch):
    """版本不匹配的 Beat 心跳被拒：不写 beat_hb（避免假信号），改写版本标记。"""
    conn = MagicMock()
    monkeypatch.setattr("django_redis.get_redis_connection", lambda name: conn)

    ops_heartbeat.apply(
        headers={"hub-env": settings.CELERY_ENV_TAG, "hub-version": "stale-beat"},
        throw=True,
    )

    assert conn.pipeline.called is False  # 正常心跳键一律不写
    assert conn.set.call_count == 1
    key, payload = conn.set.call_args.args[0], conn.set.call_args.args[1]
    assert key.endswith("ops:beat_mismatch")
    assert conn.set.call_args.kwargs.get("ex") == 900
    assert "stale-beat" in payload and settings.HUB_CODE_VERSION in payload


@pytest.mark.django_db
@override_settings(CELERY_ENV_TAG="dev", HUB_CODE_VERSION="v1")
def test_ops_heartbeat_env_mismatch_writes_nothing(monkeypatch):
    """跨环境心跳既不写心跳键也不写版本标记：别环境的数据不落本环境缓存。"""
    conn = MagicMock()
    monkeypatch.setattr("django_redis.get_redis_connection", lambda name: conn)

    ops_heartbeat.apply(headers={"hub-env": "prod", "hub-version": "v1"}, throw=True)

    assert conn.set.called is False
    assert conn.pipeline.called is False


@pytest.mark.django_db
def test_beat_card_distinguishes_version_mismatch_from_dead_beat():
    now = timezone.now()
    mismatch = {
        "beat_version": "old-hash", "worker_version": "new-hash",
        "env": "dev", "ts": now.isoformat(),
    }
    # Beat 心跳未上报（被拒）+ 标记仍新鲜 → 明确指出重启 Beat，而非笼统的心跳丢失
    card = check_celery_beat(None, mismatch)
    assert card["status"] == "error"
    assert "重启 Beat" in card["message"] and "old-hash" in card["message"]
    labels = {metric["label"]: metric["value"] for metric in card["metrics"]}
    assert labels["Beat 版本"] == "old-hash"
    assert labels["Worker 版本"] == "new-hash"

    # 心跳正常但标记新鲜 → Worker 版本混布，降级为 warn
    mixed = check_celery_beat(now, mismatch)
    assert mixed["status"] == "warn"
    assert "版本不匹配" in mixed["message"]

    # 标记过期（旧 Beat 已停止或已修复）→ 回到常规判定
    expired = {"ts": (now - timedelta(seconds=600)).isoformat(),
               "beat_version": "old", "worker_version": "new"}
    assert check_celery_beat(None, expired)["status"] == "warn"  # 未上报 → 常规 warn
    assert check_celery_beat(now, expired)["status"] == "ok"


def test_percent_threshold_judgement():
    assert _judge_percent(10, 75, 90) == "ok"
    assert _judge_percent(75, 75, 90) == "warn"
    assert _judge_percent(90, 90, 90) == "error"
    assert _judge_percent(None, 75, 90) == "error"
