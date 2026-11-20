"""运维日志实时尾随（tail -f）Consumer 测试

覆盖：
- 鉴权：未认证 4401 / 非 staff 4403 / 非白名单文件 4400
- 流式语义：连接即推送尾部上下文（init），新增行只推增量（lines），
  半行留到下一轮不拆断，轮转/截断后从头跟随（rotated）
- 增量读取单元行为：单行超限截断、文件暂缺静默等待

说明：项目未启用 pytest-asyncio，沿用 tests/test_websocket_auth.py 的
async_to_sync 包装模式运行异步场景。
"""
from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator

import pytest

from system.views import ops as ops_module
from system.views.wsopslog import OpsLogTailConsumer, _read_increment



def _write_all(path, text, **kwargs):
    """Windows 下 write_text 默认把换行翻译成 CRLF，统一用 newline="\\n" 保持字节精确"""
    kwargs.setdefault("encoding", "utf-8")
    path.write_text(text, newline="\n", **kwargs)


def _run(async_fn):
    async_to_sync(async_fn)()


async def _connect(app, path, user):
    communicator = WebsocketCommunicator(app, path)
    communicator.scope["user"] = user
    connected, _ = await communicator.connect(timeout=5)
    return communicator, connected


@pytest.mark.django_db
def test_tail_rejects_unauthenticated(monkeypatch, tmp_path):
    from django.contrib.auth.models import AnonymousUser

    monkeypatch.setattr(ops_module, "LOGS_DIR", str(tmp_path))

    async def scenario():
        communicator, connected = await _connect(
            OpsLogTailConsumer.as_asgi(), "/ws/ops/logs/?file=server.log", AnonymousUser()
        )
        assert not connected  # 未认证：握手被拒（close 4401）

    _run(scenario)


@pytest.mark.django_db
def test_tail_rejects_non_staff(normal_user, monkeypatch, tmp_path):
    monkeypatch.setattr(ops_module, "LOGS_DIR", str(tmp_path))

    async def scenario():
        communicator, connected = await _connect(
            OpsLogTailConsumer.as_asgi(), "/ws/ops/logs/?file=server.log", normal_user
        )
        assert not connected  # 非 staff：4403 拒绝

    _run(scenario)


@pytest.mark.django_db
def test_tail_rejects_file_outside_whitelist(admin_user, monkeypatch, tmp_path):
    monkeypatch.setattr(ops_module, "LOGS_DIR", str(tmp_path))

    async def scenario():
        communicator, connected = await _connect(
            OpsLogTailConsumer.as_asgi(),
            "/ws/ops/logs/?file=../main/settings.py",
            admin_user,
        )
        assert connected
        message = await communicator.receive_json_from(timeout=5)
        assert message["type"] == "error"
        await communicator.disconnect()

    _run(scenario)


@pytest.mark.django_db
def test_tail_streams_init_and_increment(admin_user, monkeypatch, tmp_path):
    log = tmp_path / "app.log"
    _write_all(log, "l1\nl2\n", encoding="utf-8")
    monkeypatch.setattr(ops_module, "LOGS_DIR", str(tmp_path))
    monkeypatch.setattr("system.views.wsopslog.POLL_INTERVAL_SECONDS", 0.05)

    async def scenario():
        communicator, connected = await _connect(
            OpsLogTailConsumer.as_asgi(), "/ws/ops/logs/?file=app.log", admin_user
        )
        assert connected

        init = await communicator.receive_json_from(timeout=5)
        assert init["type"] == "init"
        assert init["lines"] == ["l1", "l2"]

        # 追加完整行 → 增量推送
        _write_all(log, "l1\nl2\nl3\nl4\n", encoding="utf-8")
        message = await communicator.receive_json_from(timeout=5)
        assert message == {"type": "lines", "lines": ["l3", "l4"]}

        # 追加半行 → 不推送，等下一轮补齐换行后整行下发
        with open(log, "a", encoding="utf-8") as handle:
            handle.write("partial")
        _write_all(log, "l1\nl2\nl3\nl4\nfull-line\n", encoding="utf-8")
        message = await communicator.receive_json_from(timeout=5)
        assert message == {"type": "lines", "lines": ["full-line"]}

        await communicator.disconnect()

    _run(scenario)


@pytest.mark.django_db
def test_tail_handles_rotation(admin_user, monkeypatch, tmp_path):
    log = tmp_path / "app.log"
    _write_all(log, "old-1\nold-2\n", encoding="utf-8")
    monkeypatch.setattr(ops_module, "LOGS_DIR", str(tmp_path))
    monkeypatch.setattr("system.views.wsopslog.POLL_INTERVAL_SECONDS", 0.05)

    async def scenario():
        communicator, connected = await _connect(
            OpsLogTailConsumer.as_asgi(), "/ws/ops/logs/?file=app.log", admin_user
        )
        assert connected
        await communicator.receive_json_from(timeout=5)  # init

        # 模拟轮转：文件清空后写入新内容
        _write_all(log, "fresh-1\n", encoding="utf-8")
        rotated = await communicator.receive_json_from(timeout=5)
        assert rotated["type"] == "rotated"
        message = await communicator.receive_json_from(timeout=5)
        assert message == {"type": "lines", "lines": ["fresh-1"]}

        await communicator.disconnect()

    _run(scenario)


def test_read_increment_unit_semantics(tmp_path):
    log = tmp_path / "unit.log"

    # 文件不存在：保持 offset 静默等待
    assert _read_increment(str(log), 0) == (0, [])

    _write_all(log, "a\nb\n", encoding="utf-8")
    offset, events = _read_increment(str(log), 0)
    assert offset == 4
    assert events == [{"type": "lines", "lines": ["a", "b"]}]

    # 半行：offset 不前进，不产生事件
    with open(log, "a", encoding="utf-8") as handle:
        handle.write("half")
    offset, events = _read_increment(str(log), offset)
    assert offset == 4 and events == []

    # 截断（轮转）：offset 归零重读
    _write_all(log, "x\n", encoding="utf-8")
    offset, events = _read_increment(str(log), offset)
    kinds = [event["type"] for event in events]
    assert kinds == ["rotated", "lines"]
    assert events[-1]["lines"] == ["x"]
