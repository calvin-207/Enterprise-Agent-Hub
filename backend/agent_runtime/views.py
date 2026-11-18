"""REST read/submit interface. Run state is authoritative in PostgreSQL."""
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from agent_catalog.models import Agent, AgentVersion
from agent_catalog.services import is_granted, is_platform_admin
from agent_catalog.views import PlatformAPI
from agent_runtime.models import AgentRun
from agent_runtime.services import RunRejected, start_run, request_cancel


def render_run(obj):
    return {
        "id": str(obj.pk), "agent_id": str(obj.agent_id),
        "agent_version_id": str(obj.version_id), "status": obj.status,
        "status_version": obj.status_version, "result": obj.result,
        "error_code": obj.error_code, "created_at": obj.created_at,
        "started_at": obj.started_at, "finished_at": obj.finished_at,
    }


def visible_runs(user):
    if is_platform_admin(user):
        return AgentRun.objects.all()
    return AgentRun.objects.filter(requested_by=user)


class RunListAPI(PlatformAPI):
    def get(self, request):
        qs = visible_runs(request.user).order_by("-created_at")[:100]
        return Response({"code": 2000, "msg": "success", "data": [render_run(x) for x in qs]})

    def post(self, request):
        agent_id = request.data.get("agent_id")
        raw = request.data.get("input")
        from uuid import UUID
        try:
            agent_uuid = UUID(str(agent_id))
        except (ValueError, TypeError):
            return Response({"code": 400, "msg": "agent_id 格式无效"}, status=400)
        agent = get_object_or_404(Agent, pk=agent_uuid)
        # Deny even idempotency replay after grant revocation.
        if not is_granted(request.user, agent):
            raise PermissionDenied("该 Agent 未授权")
        try:
            run, created = start_run(
                actor=request.user, agent=agent, payload=raw,
                idempotency_key=request.headers.get("Idempotency-Key"),
                deadline_seconds=request.data.get("deadline_seconds", 120),
            )
        except RunRejected as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=exc.http_status,
            )
        return Response(
            {"code": 2000, "msg": "success", "data": render_run(run)},
            status=status.HTTP_202_ACCEPTED if created else status.HTTP_200_OK,
        )


class RunDetailAPI(PlatformAPI):
    def get(self, request, run_id):
        run = get_object_or_404(visible_runs(request.user), pk=run_id)
        return Response({"code": 2000, "msg": "success", "data": render_run(run)})


class RunStepsAPI(PlatformAPI):
    def get(self, request, run_id):
        run = get_object_or_404(visible_runs(request.user), pk=run_id)
        return Response({"code": 2000, "msg": "success", "data": [
            {"sequence": s.sequence, "kind": s.kind, "status": s.status,
             "details": s.details, "created_at": s.created_at}
            for s in run.steps.order_by("sequence")[:500]
        ]})


class RunEventsAPI(PlatformAPI):
    def get(self, request, run_id):
        run = get_object_or_404(visible_runs(request.user), pk=run_id)
        try:
            after = int(request.query_params.get("after", 0))
            limit = int(request.query_params.get("limit", 100))
        except (ValueError, TypeError):
            return Response({"code": 400, "msg": "分页参数不合法"}, status=400)
        if after < 0 or not 1 <= limit <= 200:
            return Response({"code": 400, "msg": "分页参数不合法"}, status=400)
        return Response({"code": 2000, "msg": "success", "data": [
            {"sequence": e.sequence, "type": e.kind, "payload": e.payload,
             "created_at": e.created_at}
            for e in run.events.filter(sequence__gt=after).order_by("sequence")[:limit]
        ]})


class RunCancelAPI(PlatformAPI):
    def post(self, request, run_id):
        run = get_object_or_404(visible_runs(request.user), pk=run_id)
        return Response({"code": 2000, "msg": "success",
                         "data": render_run(request_cancel(run.pk))})


class RunUsageAPI(PlatformAPI):
    def get(self, request, run_id):
        run = get_object_or_404(visible_runs(request.user), pk=run_id)
        usage = getattr(run, "model_usage", None)
        if usage is None:
            return Response({"code": 2000, "msg": "success", "data": None})
        return Response({"code": 2000, "msg": "success", "data": {
            "provider": usage.provider_code, "model": usage.model_code,
            "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
            "estimated_cost": str(usage.estimated_cost) if usage.estimated_cost is not None else None,
            "input_price_per_million": str(usage.input_price_per_million),
            "output_price_per_million": str(usage.output_price_per_million),
            "currency": "USD", "estimated": True,
        }})
