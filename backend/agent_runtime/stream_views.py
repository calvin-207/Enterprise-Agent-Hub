"""Authenticated ASGI-friendly SSE tail with durable RunEvent cursor.

The async generator ensures Daphne/ASGI streams each event without buffering a
synchronous iterator. JWT is accepted only through request Authorization header.
"""
import asyncio
import json
import time

from asgiref.sync import sync_to_async
from django.db import close_old_connections
from django.http import StreamingHttpResponse
from rest_framework.response import Response
from agent_catalog.views import PlatformAPI
from agent_runtime.models import AgentRun, RunEvent
from agent_runtime.views import visible_runs


TERMINAL = {AgentRun.Status.SUCCEEDED, AgentRun.Status.FAILED, AgentRun.Status.CANCELLED}


def _read_batch(run_id, after):
    """Perform all ORM access in a thread-sensitive sync context."""
    close_old_connections()
    try:
        batch = list(RunEvent.objects.filter(
            run_id=run_id, sequence__gt=after
        ).order_by("sequence").values("sequence", "kind", "payload")[:100])
        current = AgentRun.objects.filter(pk=run_id).values_list("status", flat=True).first()
        return batch, current
    finally:
        close_old_connections()


async def sse_chunks(run_id, after=0, *, max_seconds=15):
    last = after
    stop_at = time.monotonic() + max_seconds
    while True:
        batch, status = await sync_to_async(_read_batch, thread_sensitive=True)(run_id, last)
        for item in batch:
            last = item["sequence"]
            payload = json.dumps({
                "sequence": item["sequence"], "type": item["kind"],
                "payload": item["payload"],
            }, ensure_ascii=False)
            yield "id: {}\nevent: run-event\ndata: {}\n\n".format(last, payload)
        if status in TERMINAL and not batch:
            yield "event: stream-end\ndata: {}\n\n"
            return
        if time.monotonic() >= stop_at:
            yield ": reconnect\n\n"
            return
        if not batch:
            await asyncio.sleep(0.5)


class RunStreamAPI(PlatformAPI):
    def get(self, request, run_id):
        if not visible_runs(request.user).filter(pk=run_id).exists():
            from django.http import Http404
            raise Http404
        raw = request.headers.get("Last-Event-ID") or request.query_params.get("after", "0")
        try:
            after = int(raw)
        except (ValueError, TypeError):
            return Response({"code": 400, "msg": "after 游标无效"}, status=400)
        if not 0 <= after <= 2**31 - 1:
            return Response({"code": 400, "msg": "after 游标无效"}, status=400)
        response = StreamingHttpResponse(sse_chunks(run_id, after), content_type="text/event-stream; charset=utf-8")
        response["Cache-Control"] = "no-cache, no-transform"
        response["X-Accel-Buffering"] = "no"
        response["X-Content-Type-Options"] = "nosniff"
        return response
