# -*- coding: utf-8 -*-

"""
@Remark: 运维管理 —— 实时日志尾随（tail -f）WebSocket Consumer

前端通过 /ws/ops/logs/?file=server.log 建立连接：
- 连接后立即推送文件尾部（默认 200 行）作为上下文（type=init）；
- 之后每秒增量读取，仅推送新追加的完整行（type=lines）；
- 检测到轮转/截断（文件变小）时从头重读并提示（type=rotated）；
- 文件暂时消失（轮转间隙）静默等待重建；
- 白名单与 OpsLogsView 完全一致：只允许 LOGS_DIR 下已枚举的 .log 文件。

鉴权：JwtAuthMiddleware 已完成子协议认证；此处二次校验登录与 staff 身份，
与 REST 接口 /api/system/ops/logs/ 的 IsAdminUser 保持同一口径。
"""

import asyncio
import os
from urllib.parse import parse_qs

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from system.views import ops as ops_module
from system.views.ops import (
    LOG_DEFAULT_LINES,
    MAX_BATCH_LINES,
    MAX_BATCH_BYTES,
    POLL_INTERVAL_SECONDS,
    _decode_text,
    _list_log_files,
    _tail_lines,
)


def _read_increment(path, offset):
    """读取 offset 之后的新内容，返回 (new_offset, events)。

    只发送完整行：块尾没有换行符的半行留到下一轮，避免日志行被拆断。
    """
    events = []
    try:
        size = os.path.getsize(path)
    except OSError:
        return offset, []  # 轮转间隙文件暂缺：保持 offset，下轮重试

    if size < offset:
        offset = 0
        events.append(
            {"type": "rotated", "message": "检测到日志轮转/清空，已从头开始跟随"}
        )
    if size == offset:
        return offset, events

    try:
        with open(path, "rb") as handle:
            handle.seek(offset)
            chunk = handle.read(MAX_BATCH_BYTES + 1)
            end = handle.tell()
    except OSError:
        return offset, []

    if chunk.endswith(b"\n") or end - offset > MAX_BATCH_BYTES:
        # 全是完整行；或单行超长（> 256KB 无换行）——极端情况按整段发送
        new_offset = end
    else:
        cut = chunk.rfind(b"\n")
        if cut == -1:
            new_offset = offset  # 数据不足一行，等下一轮
            chunk = b""
        else:
            chunk = chunk[: cut + 1]
            new_offset = offset + len(chunk)

    lines = _decode_text(chunk).splitlines() if chunk else []
    if not lines:
        return new_offset, events

    if len(lines) > MAX_BATCH_LINES:
        events.append(
            {
                "type": "notice",
                "message": f"单次增量超过 {MAX_BATCH_LINES} 行，已截断显示（{len(lines)} → {MAX_BATCH_LINES}）",
            }
        )
        lines = lines[-MAX_BATCH_LINES:]
    events.append({"type": "lines", "lines": lines})
    return new_offset, events


class OpsLogTailConsumer(AsyncJsonWebsocketConsumer):
    """单连接尾随单个日志文件；不经 channel layer，断开即取消读取任务"""

    async def connect(self):
        user = self.scope.get("user", None)
        if not user or not user.is_authenticated:
            return await self.close(code=4401)
        if not user.is_staff:
            return await self.close(code=4403)

        file_name = self._file_param()
        known = {item["name"] for item in await self._known_files()}
        if file_name not in known:
            await self.accept("JWTLEEADMIN")
            await self.send_json({"type": "error", "message": "日志文件不存在或不可读"})
            return await self.close(code=4400)

        self.file_name = file_name
        # 运行时取 LOGS_DIR（而非导入时绑定），保证与 _list_log_files 的白名单一致
        self.path = os.path.join(ops_module.LOGS_DIR, file_name)
        self.tail_task = None
        await self.accept("JWTLEEADMIN")

        lines = await asyncio.to_thread(_tail_lines, self.path, LOG_DEFAULT_LINES)
        await self.send_json({"type": "init", "file": file_name, "lines": lines})
        # 起始 offset 必须在 connect 时立即锁定：若推迟到首轮 poll 再取 size，
        # 连接建立到首次轮询之间追加的日志会被误认为“已推送”而丢失
        offset = await asyncio.to_thread(self._current_size)
        self.tail_task = asyncio.create_task(self._tail_loop(offset))

    async def disconnect(self, close_code):
        task = getattr(self, "tail_task", None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def receive_json(self, content, **kwargs):
        # 前端心跳/占位消息：无需应答
        pass

    # ---------------- 内部工具 ----------------

    async def _tail_loop(self, offset):
        while True:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            offset, events = await asyncio.to_thread(
                _read_increment, self.path, offset
            )
            for event in events:
                await self.send_json(event)

    def _current_size(self):
        return os.path.getsize(self.path)

    def _file_param(self):
        query = self.scope.get("query_string", b"").decode("utf-8", errors="replace")
        return (parse_qs(query).get("file") or [""])[0].strip()

    @staticmethod
    async def _known_files():
        return await asyncio.to_thread(_list_log_files)
