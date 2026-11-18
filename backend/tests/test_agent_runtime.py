"""P1-B Run/Outbox invariants without paid model calls or real broker."""
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from agent_catalog.models import Agent, AgentAccessGrant, AgentVersion
from agent_runtime.models import AgentRun, RunEvent, RunStep, DispatchOutbox
from agent_runtime.dispatcher import dispatch_pending
from agent_runtime.services import claim_run, finish_run, expire_abandoned_runs
from agent_runtime.tasks import execute_agent_run
from model_gateway.models import ModelProfile
from tool_gateway.models import ToolDefinition


@pytest.fixture
def admin(django_user_model):
    return django_user_model.objects.create_superuser(
        username="run-admin", password="TestPassword!2026", name="Run Admin"
    )


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(
        username="run-user", password="TestPassword!2026", name="Run User"
    )


@pytest.fixture
def ready_agent(admin, user, db):
    call_command("bootstrap_mock_catalog")
    agent = Agent.objects.create(code="run-demo", name="Runtime P1B", owner=admin, status=Agent.Status.ACTIVE)
    version = AgentVersion.objects.create(
        agent=agent, version_number=1, status=AgentVersion.Status.DRAFT,
        model_profile=ModelProfile.objects.get(model_code="mock-small"),
        system_prompt="Read-only mock analysis", created_by=admin,
    )
    from agent_catalog.models import ToolGrant
    ToolGrant.objects.create(version=version, tool=ToolDefinition.objects.get(code="mock_sales_summary"))
    from agent_catalog.services import publish_version
    Agent.objects.filter(pk=agent.pk).update(status=Agent.Status.DRAFT)
    publish_version(agent, version.pk)
    AgentAccessGrant.objects.create(agent=agent, user=user, capability="run")
    return agent


@pytest.fixture
def client_user(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def post_run(client, agent_id, key="run-key-1", message="销售分析", deadline=120):
    return client.post(
        "/api/platform/v1/runs/",
        {"agent_id": str(agent_id), "input": {"message": message}, "deadline_seconds": deadline},
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )


@pytest.mark.django_db
def test_create_and_idempotency(client_user, ready_agent, user):
    first = post_run(client_user, ready_agent.pk)
    assert first.status_code == 202, first.data
    run = AgentRun.objects.get(pk=first.data["data"]["id"])
    assert run.status == "QUEUED"
    assert run.status_version == 1
    assert run.outbox.status == "PENDING"
    assert run.version.status == "published"
    assert "prompt_sha256" in run.version_snapshot
    assert len(run.version_snapshot["tool_ids"]) == 1
    assert RunEvent.objects.filter(run=run, kind="run.queued").count() == 1

    replay = post_run(client_user, ready_agent.pk)
    assert replay.status_code == 200, replay.data
    assert replay.data["data"]["id"] == first.data["data"]["id"]
    assert post_run(client_user, ready_agent.pk, message="different").status_code == 409
    assert AgentRun.objects.count() == 1


@pytest.mark.django_db
def test_worker_claim_and_terminal_are_idempotent(client_user, ready_agent):
    run_id = post_run(client_user, ready_agent.pk).data["data"]["id"]
    with patch("agent_runtime.dispatcher.execute_agent_run.apply_async") as queued:
        assert dispatch_pending() == 1
        assert queued.call_count == 1
        assert dispatch_pending() == 0
    record = AgentRun.objects.get(pk=run_id)
    assert record.outbox.status == "SENT"

    execute_agent_run.apply(args=[run_id], throw=True)
    record.refresh_from_db()
    assert record.status == AgentRun.Status.SUCCEEDED
    assert record.error_code == ""
    assert record.status_version == 3
    assert record.result["mock"] is True
    assert record.result["evidence"] == ["synthetic:mock_sales_summary"]
    assert list(record.events.values_list("sequence", flat=True)) == [1, 2, 3, 4, 5]
    assert list(record.steps.values_list("sequence", flat=True)) == [1, 2, 3]
    assert list(record.steps.values_list("kind", flat=True)) == ["DISPATCH", "TOOL_READ", "MODEL_CALL"]

    execute_agent_run.apply(args=[run_id], throw=True)
    record.refresh_from_db()
    assert record.status_version == 3
    assert record.events.count() == 5


@pytest.mark.django_db
def test_broker_failure_retry_and_recovery(client_user, ready_agent):
    run_id = post_run(client_user, ready_agent.pk).data["data"]["id"]
    with patch("agent_runtime.dispatcher.execute_agent_run.apply_async", side_effect=ConnectionError("broker down")):
        assert dispatch_pending() == 0
    row = DispatchOutbox.objects.get(run_id=run_id)
    assert row.status == "PENDING"
    assert row.attempts == 1
    assert row.next_attempt_at > timezone.now()
    assert row.last_error == "BROKER_UNAVAILABLE"
    with patch("agent_runtime.dispatcher.execute_agent_run.apply_async") as queued:
        assert dispatch_pending() == 0
        DispatchOutbox.objects.filter(pk=row.pk).update(next_attempt_at=timezone.now() - timedelta(seconds=1))
        assert dispatch_pending() == 1
        assert queued.call_count == 1


@pytest.mark.django_db
def test_lease_duplicate_claim_and_expired_cleanup(client_user, ready_agent):
    import uuid
    run_id = post_run(client_user, ready_agent.pk).data["data"]["id"]
    first_token, second_token = uuid.uuid4(), uuid.uuid4()
    assert claim_run(run_id, first_token)
    assert not claim_run(run_id, second_token)
    assert not finish_run(run_id, second_token, status=AgentRun.Status.SUCCEEDED)
    AgentRun.objects.filter(pk=run_id).update(lease_until=timezone.now() - timedelta(seconds=2))
    assert expire_abandoned_runs() == 1
    record = AgentRun.objects.get(pk=run_id)
    assert record.status == AgentRun.Status.FAILED
    assert record.error_code == "WORKER_LEASE_EXPIRED"
    assert expire_abandoned_runs() == 0


@pytest.mark.django_db
def test_non_owner_cannot_access_run_and_revoke_prevents_new_run(client_user, ready_agent, user, django_user_model):
    first = post_run(client_user, ready_agent.pk)
    run_id = first.data["data"]["id"]
    other = django_user_model.objects.create_user(
        username="run-stranger", password="pw", name="Stranger"
    )
    c = APIClient()
    assert c.get(f"/api/platform/v1/runs/{run_id}/").status_code == 401
    c.force_authenticate(user=other)
    for path in (f"/api/platform/v1/runs/{run_id}/", f"/api/platform/v1/runs/{run_id}/steps/", f"/api/platform/v1/runs/{run_id}/events/"):
        assert c.get(path).status_code == 404
    AgentAccessGrant.objects.filter(agent=ready_agent, user=user).delete()
    assert post_run(client_user, ready_agent.pk).status_code == 403
    assert post_run(client_user, ready_agent.pk, key="new").status_code == 403


@pytest.mark.django_db
def test_invalid_inputs_and_event_cursor(client_user, ready_agent):
    assert post_run(client_user, ready_agent.pk, key="").status_code == 400
    assert post_run(client_user, ready_agent.pk, deadline=0).status_code == 400
    assert post_run(client_user, ready_agent.pk, deadline=271).status_code == 400
    run_id = post_run(client_user, ready_agent.pk).data["data"]["id"]
    assert client_user.get(f"/api/platform/v1/runs/{run_id}/events/?after=0").status_code == 200
    assert len(client_user.get(f"/api/platform/v1/runs/{run_id}/events/?after=1").data["data"]) == 0
    assert client_user.get(f"/api/platform/v1/runs/{run_id}/events/?after=-1").status_code == 400
    assert client_user.get(f"/api/platform/v1/runs/{run_id}/events/?limit=201").status_code == 400
