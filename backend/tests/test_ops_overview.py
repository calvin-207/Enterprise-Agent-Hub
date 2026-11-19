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


def test_percent_threshold_judgement():
    assert _judge_percent(10, 75, 90) == "ok"
    assert _judge_percent(75, 75, 90) == "warn"
    assert _judge_percent(90, 90, 90) == "error"
    assert _judge_percent(None, 75, 90) == "error"
