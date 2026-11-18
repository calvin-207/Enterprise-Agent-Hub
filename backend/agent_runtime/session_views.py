"""Owner-isolated conversations. Archived conversations are read-only."""
from uuid import UUID
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from agent_catalog.models import Agent
from agent_catalog.services import is_granted
from agent_catalog.views import PlatformAPI
from agent_runtime.models import AgentSession, AgentMessage
from agent_runtime.services import start_run, RunRejected
from agent_runtime.views import render_run


def ok(value, status=200):
    return Response({"code": 2000, "msg": "success", "data": value}, status=status)


def bad(message, code=400):
    return Response({"code": code, "msg": str(message)}, status=code)


def session_data(s):
    return {"id": str(s.pk), "agent_id": str(s.agent_id), "title": s.title,
            "archived": s.archived, "created_at": s.created_at, "updated_at": s.updated_at}


def owner_sessions(user):
    # Even platform admins cannot see another user's private conversation via this API.
    return AgentSession.objects.filter(owner=user)


class SessionListAPI(PlatformAPI):
    def get(self, request):
        qs = owner_sessions(request.user).filter(archived=False).order_by("-updated_at")[:100]
        return ok([session_data(s) for s in qs])

    def post(self, request):
        raw = request.data.get("agent_id")
        try:
            agent_id = UUID(str(raw))
        except (ValueError, TypeError, AttributeError):
            return bad("agent_id 格式无效")
        agent = get_object_or_404(Agent, pk=agent_id)
        if agent.status != Agent.Status.ACTIVE or not is_granted(request.user, agent):
            raise PermissionDenied("Agent 不可用或未授权")
        title = request.data.get("title", "新会话")
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > 120:
            return bad("标题不能为空且不可超过 120 字符")
        session = AgentSession.objects.create(agent=agent, owner=request.user, title=title.strip())
        return ok(session_data(session), 201)


class SessionDetailAPI(PlatformAPI):
    def get(self, request, session_id):
        return ok(session_data(get_object_or_404(owner_sessions(request.user), pk=session_id)))

    def patch(self, request, session_id):
        session = get_object_or_404(owner_sessions(request.user), pk=session_id)
        if session.archived:
            return bad("会话已归档，不能修改", 409)
        allowed = {"title", "archived"}
        if not isinstance(request.data, dict) or set(request.data) - allowed:
            return bad("只允许修改标题或归档状态")
        fields = []
        if "title" in request.data:
            title = request.data["title"]
            if not isinstance(title, str) or not title.strip() or len(title.strip()) > 120:
                return bad("标题不能为空且不可超过 120 字符")
            session.title = title.strip()
            fields.append("title")
        if "archived" in request.data:
            if request.data["archived"] is not True:
                return bad("会话归档不可恢复")
            if session.runs.filter(status__in=("QUEUED", "RUNNING", "CANCEL_REQUESTED")).exists():
                return bad("会话仍有执行中任务", 409)
            session.archived = True
            fields.append("archived")
        if fields:
            session.save(update_fields=fields + ["updated_at"])
        return ok(session_data(session))


class SessionMessagesAPI(PlatformAPI):
    def get(self, request, session_id):
        session = get_object_or_404(owner_sessions(request.user), pk=session_id)
        try:
            after = int(request.query_params.get("after", 0))
            limit = int(request.query_params.get("limit", 50))
        except (TypeError, ValueError):
            return bad("分页参数不合法")
        if after < 0 or not 1 <= limit <= 100:
            return bad("分页参数不合法")
        messages = session.messages.filter(pk__gt=after).order_by("pk")[:limit]
        return ok([{"id": m.pk, "run_id": str(m.run_id), "role": m.role,
                    "content": m.content, "created_at": m.created_at}
                   for m in messages])


class SessionRunAPI(PlatformAPI):
    def post(self, request, session_id):
        session = get_object_or_404(owner_sessions(request.user), pk=session_id)
        if session.archived or not is_granted(request.user, session.agent):
            raise PermissionDenied("会话已归档或 Agent 未授权")
        if not isinstance(request.data, dict):
            return bad("输入格式不合法")
        # Session-scoped run submission; existing /runs/ remains backward-compatible.
        try:
            run, created = start_run(
                actor=request.user, agent=session.agent,
                payload={"message": request.data.get("message")},
                idempotency_key=request.headers.get("Idempotency-Key"),
                deadline_seconds=request.data.get("deadline_seconds", 120),
                session=session,
            )
        except RunRejected as exc:
            return Response({"error": {"code": exc.code, "message": exc.message}}, status=exc.http_status)
        return ok(render_run(run), 202 if created else 200)
