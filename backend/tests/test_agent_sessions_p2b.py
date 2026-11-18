"""P2-B regression: isolation, turn persistence, history, idempotency and cursor SSE."""
import uuid
import pytest
from asgiref.sync import async_to_sync
from django.core.management import call_command
from rest_framework.test import APIClient

from agent_catalog.models import Agent, AgentAccessGrant, AgentVersion, ToolGrant
from agent_catalog.services import publish_version
from agent_runtime.models import AgentRun, AgentMessage, AgentSession
from agent_runtime.tasks import execute_agent_run
from model_gateway.models import ModelProfile
from tool_gateway.models import ToolDefinition


@pytest.fixture
def setup_chat(db, django_user_model):
    owner = django_user_model.objects.create_superuser(
        username="chat-admin", password="StrongPass!2026", name="Admin"
    )
    alice = django_user_model.objects.create_user(
        username="chat-alice", password="StrongPass!2026", name="Alice"
    )
    bob = django_user_model.objects.create_user(
        username="chat-bob", password="StrongPass!2026", name="Bob"
    )
    call_command("bootstrap_mock_catalog")
    agent = Agent.objects.create(code="chat-demo", name="会话Agent", owner=owner)
    version = AgentVersion.objects.create(
        agent=agent, version_number=1, system_prompt="Analyse synthetic data",
        model_profile=ModelProfile.objects.get(model_code="mock-small"),
        created_by=owner,
    )
    ToolGrant.objects.create(version=version, tool=ToolDefinition.objects.get(code="mock_sales_summary"))
    publish_version(agent, version.pk)
    for user in (alice, bob):
        AgentAccessGrant.objects.create(agent=agent, user=user, capability="run")
    return agent, owner, alice, bob


def auth(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def session(client, agent):
    response = client.post("/api/platform/v1/sessions/", {
        "agent_id": str(agent.pk), "title": "销售分析"
    }, format="json")
    assert response.status_code == 201, response.data
    return response.data["data"]["id"]


async def _consume_stream(content):
    chunks = []
    async for part in content:
        chunks.append(part if isinstance(part, bytes) else part.encode("utf-8"))
    return b"".join(chunks).decode("utf-8")


def send(client, sid, msg, key):
    return client.post(
        f"/api/platform/v1/sessions/{sid}/runs/",
        {"message": msg}, format="json", HTTP_IDEMPOTENCY_KEY=key,
    )


@pytest.mark.django_db
def test_session_turns_history_and_refresh(setup_chat):
    agent, admin, alice, bob = setup_chat
    client = auth(alice)
    sid = session(client, agent)
    created = send(client, sid, "分析9月销售额", "first")
    assert created.status_code == 202, created.data
    run_id = created.data["data"]["id"]
    assert send(client, sid, "分析9月销售额", "first").status_code == 200
    assert send(client, sid, "分析10月销售额", "second").status_code == 409
    assert AgentMessage.objects.filter(session_id=sid, role="user").count() == 1

    execute_agent_run.apply(args=[run_id], throw=True)
    first = AgentRun.objects.get(pk=run_id)
    assert first.status == "SUCCEEDED"
    messages = client.get(f"/api/platform/v1/sessions/{sid}/messages/").data["data"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert "2026-09" in messages[1]["content"]

    followup = send(client, sid, "继续分析刚才那个月", "second")
    assert followup.status_code == 202, followup.data
    execute_agent_run.apply(args=[followup.data["data"]["id"]], throw=True)
    second = AgentRun.objects.get(pk=followup.data["data"]["id"])
    assert second.status == "SUCCEEDED"
    assert "2026-09" in second.result["answer"]
    history = client.get(f"/api/platform/v1/sessions/{sid}/messages/?after={messages[-1]['id']}")
    assert [x["role"] for x in history.data["data"]] == ["user", "assistant"]
    assert client.get(f"/api/platform/v1/sessions/{sid}/").data["data"]["active_run_id"] is None


@pytest.mark.django_db
def test_session_owner_only_even_for_superadmin(setup_chat):
    agent, admin, alice, bob = setup_chat
    sid = session(auth(alice), agent)
    first = send(auth(alice), sid, "分析10月", "owner")
    assert first.status_code == 202
    for user in (admin, bob):
        client = auth(user)
        assert client.get(f"/api/platform/v1/sessions/{sid}/").status_code == 404
        assert client.get(f"/api/platform/v1/sessions/{sid}/messages/").status_code == 404
        assert client.post(f"/api/platform/v1/sessions/{sid}/runs/", {"message": "x"}, format="json").status_code == 404
        assert client.patch(f"/api/platform/v1/sessions/{sid}/", {"title": "steal"}, format="json").status_code == 404
    assert auth(alice).get("/api/platform/v1/sessions/").status_code == 200
    assert auth(bob).get("/api/platform/v1/sessions/").data["data"] == []
    run_id = first.data["data"]["id"]
    # Session history stays private even if the caller is platform admin.
    for user in (admin, bob):
        c = auth(user)
        assert c.get(f"/api/platform/v1/runs/{run_id}/").status_code == 404
        assert c.get(f"/api/platform/v1/runs/{run_id}/events/").status_code == 404
        assert c.get(f"/api/platform/v1/runs/{run_id}/stream/").status_code == 404


@pytest.mark.django_db
def test_archive_and_invalid_message(setup_chat):
    agent, admin, alice, bob = setup_chat
    client = auth(alice)
    sid = session(client, agent)
    assert send(client, sid, "   ", "blank").status_code == 400
    assert AgentMessage.objects.filter(session_id=sid).count() == 0
    run = send(client, sid, "分析10月", "job")
    assert run.status_code == 202
    assert client.patch(f"/api/platform/v1/sessions/{sid}/", {"archived": True}, format="json").status_code == 409
    execute_agent_run.apply(args=[run.data["data"]["id"]], throw=True)
    assert client.patch(f"/api/platform/v1/sessions/{sid}/", {"title": "历史销售"}, format="json").status_code == 200
    assert client.patch(f"/api/platform/v1/sessions/{sid}/", {"archived": True}, format="json").status_code == 200
    assert send(client, sid, "重新执行", "new").status_code == 403
    assert client.get(f"/api/platform/v1/sessions/{sid}/messages/").status_code == 200
    assert client.get("/api/platform/v1/sessions/").data["data"] == []


@pytest.mark.django_db
def test_sse_replay_id_and_terminal_finish(setup_chat):
    agent, admin, alice, bob = setup_chat
    client = auth(alice)
    sid = session(client, agent)
    run = send(client, sid, "分析10月", "events")
    run_id = run.data["data"]["id"]
    execute_agent_run.apply(args=[run_id], throw=True)
    url = f"/api/platform/v1/runs/{run_id}/stream/"
    response = client.get(url + "?after=2")
    assert response.status_code == 200
    assert response.streaming
    body = async_to_sync(_consume_stream)(response.streaming_content)
    assert "id: 3" in body
    assert "event: run-event" in body
    assert "event: stream-end" in body
    assert "id: 1\n" not in body
    replay = client.get(url, HTTP_LAST_EVENT_ID="4")
    replay_text = async_to_sync(_consume_stream)(replay.streaming_content)
    assert "id: 5\n" in replay_text
    assert "id: 4\n" not in replay_text
    assert client.get(url + "?after=-1").status_code == 400
    assert auth(bob).get(url).status_code == 404
    assert APIClient().get(url).status_code == 401


@pytest.mark.django_db
def test_failed_run_does_not_enter_context(setup_chat):
    agent, admin, alice, bob = setup_chat
    client = auth(alice)
    sid = session(client, agent)
    response = send(client, sid, "分析9月", "bad")
    # A failed run keeps the user audit message, but not an assistant reply or memory.
    from agent_runtime.services import claim_run, finish_run
    token = uuid.uuid4()
    assert claim_run(response.data["data"]["id"], token)
    assert finish_run(response.data["data"]["id"], token, status="FAILED", error_code="TEST_FAILURE")
    assert AgentMessage.objects.filter(session_id=sid, role="assistant").count() == 0
    reply = send(client, sid, "继续分析", "after-failure")
    assert reply.status_code == 202
    execute_agent_run.apply(args=[reply.data["data"]["id"]], throw=True)
    outcome = AgentRun.objects.get(pk=reply.data["data"]["id"])
    assert "2026-10" in outcome.result["answer"]  # no failed 9月 context
