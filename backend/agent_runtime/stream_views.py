"""Authenticated, bounded SSE tail of persisted RunEvent with cursor replay.

This endpoint streams *run events*, not raw LLM tokens. The browser must send
Authorization header (native EventSource cannot do that). Never accept token in URL.
"""
import json
import time
from django.db import close_old_connections
from django.http import StreamingHttpResponse
from rest_framework.response import Response
from agent_catalog.views import PlatformAPI
from agent_runtime.models import AgentRun, RunEvent
from agent_runtime.views import visible_runs


TERMINAL = {AgentRun.Status.SUCCEEDED, AgentRun.Status.FAILED, AgentRun.Status.CANCELLED}


def sse_chunks(run_id, after=0, *, max_seconds=15):
    last = after
    stop_at = time.monotonic() + max_seconds
    try:
        while True:
            close_old_connections()
            batch = list(RunEvent.objects.filter(
                run_id=run_id, sequence__gt=last
            ).order_by("sequence")[:100])
            for item in batch:
                last = item.sequence
                payload = json.dumps({"sequence": item.sequence, "type": item.kind,
                                      "payload": item.payload}, ensure_ascii=False)
                yield "id: {}\nevent: run-event\ndata: {}\n\n".format(item.sequence, payload)
            status = AgentRun.objects.filter(pk=run_id).values_list("status", flat=True).first()
            if status in TERMINAL and not batch:
                yield "event: stream-end\ndata: {}\n\n"
                break
            if time.monotonic() >= stop_at:
                yield ": reconnect\n\n"
                break
            if not batch:
                time.sleep(0.5)
    finally:
        close_old_connections()


class RunStreamAPI(PlatformAPI):
    def get(self, request, run_id):
        # Owner check occurs before the streaming response is opened.
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
