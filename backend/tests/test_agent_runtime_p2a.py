"""P2-A: secret refs, model administration, metering, admission and cancellation."""
from decimal import Decimal
import uuid
from unittest.mock import patch

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from agent_catalog.models import Agent, AgentAccessGrant, AgentVersion, ToolGrant
from agent_catalog.services import publish_version
from agent_runtime.accounting import save_usage
from agent_runtime.dispatcher import dispatch_pending
from agent_runtime.models import AgentRun, ModelUsage, RunEvent
from agent_runtime.services import RunRejected, claim_run, finish_run, request_cancel, start_run
from agent_runtime.tasks import execute_agent_run
from model_gateway.models import ModelProfile, ModelProvider
from model_gateway.secrets import resolve_secret, validate_secret_ref
from tool_gateway.models import ToolDefinition


@pytest.fixture
def users(django_user_model):
    admin = django_user_model.objects.create_superuser(
        username="p2a-admin", password="StrongPassword!2026", name="P2A Admin"
    )
    user = django_user_model.objects.create_user(
        username="p2a-user", password="StrongPassword!2026", name="P2A User"
    )
    return admin, user


@pytest.fixture
def ready(users, db):
    admin, user = users
    call_command("bootstrap_mock_catalog")
    profile = ModelProfile.objects.get(model_code="mock-small")
    profile.input_price_per_million = Decimal("2.000000")
    profile.output_price_per_million = Decimal("8.000000")
    profile.save()
    agent = Agent.objects.create(code="p2a-agent", name="P2A", owner=admin)
    version = AgentVersion.objects.create(
        agent=agent, version_number=1, model_profile=profile,
        system_prompt="Use synthetic data", created_by=admin,
    )
    ToolGrant.objects.create(
        version=version, tool=ToolDefinition.objects.get(code="mock_sales_summary")
    )
    publish_version(agent, version.pk)
    agent.refresh_from_db()
    version.refresh_from_db()
    AgentAccessGrant.objects.create(agent=agent, user=user, capability="run")
    return agent, version, admin, user


def new_run(ready, key="p2a-run"):
    agent, version, admin, user = ready
    return start_run(actor=user, agent=agent, payload={"message": "分析10月销售"},
                     idempotency_key=key)[0]


@pytest.mark.django_db
def test_mock_usage_is_recorded_and_unknown_usage_stays_unknown(ready):
    run = new_run(ready)
    execute_agent_run.apply(args=[str(run.pk)], throw=True)
    run.refresh_from_db()
    assert run.status == AgentRun.Status.SUCCEEDED
    usage = ModelUsage.objects.get(run=run)
    assert usage.input_tokens == 0 and usage.output_tokens == 0
    assert usage.estimated_cost == Decimal("0")
    assert usage.input_price_per_million == Decimal("2")
    assert usage.output_price_per_million == Decimal("8")

    other = new_run(ready, key="unknown-usage")
    entry = save_usage(other, ready[1], {"input_tokens": None, "output_tokens": None})
    assert entry.estimated_cost is None
    assert entry.input_tokens is None and entry.output_tokens is None


@pytest.mark.django_db
def test_price_is_frozen_at_submission(ready):
    run = new_run(ready)
    profile = ready[1].model_profile
    profile.input_price_per_million = Decimal("99")
    profile.output_price_per_million = Decimal("99")
    profile.save(update_fields=["input_price_per_million", "output_price_per_million"])
    entry = save_usage(run, ready[1], {"input_tokens": 1000, "output_tokens": 2000})
    assert entry.input_price_per_million == Decimal("2")
    assert entry.output_price_per_million == Decimal("8")
    assert entry.estimated_cost == Decimal("0.01800000")


@pytest.mark.django_db
def test_queued_cancel_is_final_and_prevents_dispatch(ready):
    run = new_run(ready)
    result = request_cancel(run.pk)
    assert result.status == AgentRun.Status.CANCELLED
    assert result.outbox.status == "CANCELLED"
    assert RunEvent.objects.filter(run=run, kind="run.cancelled").count() == 1
    assert request_cancel(run.pk).status == "CANCELLED"
    assert RunEvent.objects.filter(run=run, kind="run.cancelled").count() == 1
    with patch("agent_runtime.dispatcher.execute_agent_run.apply_async") as dispatch:
        assert dispatch_pending() == 0
        assert dispatch.call_count == 0
    execute_agent_run.apply(args=[str(run.pk)], throw=True)
    run.refresh_from_db()
    assert run.status == "CANCELLED"


@pytest.mark.django_db
def test_running_cancel_wins_over_worker_success(ready):
    run = new_run(ready)
    token = uuid.uuid4()
    assert claim_run(run.pk, token)
    assert request_cancel(run.pk).status == "CANCEL_REQUESTED"
    assert finish_run(run.pk, token, status=AgentRun.Status.SUCCEEDED,
                      result={"answer": "late"}) is True
    run.refresh_from_db()
    assert run.status == "CANCELLED"
    assert run.result is None
    assert run.status_version == 4
    assert list(run.events.values_list("kind", flat=True)) == [
        "run.queued", "run.started", "run.cancel_requested", "run.cancelled",
    ]


@pytest.mark.django_db
def test_submission_caps_and_replay(ready):
    for i in range(3):
        run = new_run(ready, key=f"cap-{i}")
        assert run.status == "QUEUED"
    with pytest.raises(RunRejected) as error:
        new_run(ready, key="cap-4")
    assert error.value.http_status == 429
    same = new_run(ready, key="cap-1")
    assert same.id == AgentRun.objects.get(idempotency_key="cap-1").id
    assert AgentRun.objects.count() == 3


@pytest.mark.django_db
def test_provider_admin_only_and_never_accepts_raw_secret(users):
    admin, user = users
    admin_client = APIClient()
    admin_client.force_authenticate(user=admin)
    staff_client = APIClient()
    staff_client.force_authenticate(user=user)
    url = "/api/platform/v1/model-providers/"
    assert staff_client.get(url).status_code == 403
    assert staff_client.post(url, {"code": "test", "name": "Test"}, format="json").status_code == 403
    assert admin_client.post(url, {
        "code": "myopenai", "name": "Provider", "adapter_type": "openai",
        "plaintext_secret": "secret-value", "enabled": True,
    }, format="json").status_code == 400
    assert admin_client.post(url, {
        "code": "myopenai", "name": "Provider", "adapter_type": "openai",
        "secret_ref": "env:ARBITRARY_DATABASE_PASSWORD", "enabled": True,
    }, format="json").status_code == 400

    created = admin_client.post(url, {
        "code": "myopenai", "name": "Provider", "adapter_type": "openai",
        "secret_ref": "env:EAH_MODEL_KEY_MAIN", "enabled": True,
    }, format="json")
    assert created.status_code == 201, created.data
    assert "secret-value" not in str(created.data)
    provider_id = created.data["data"]["id"]
    profile = admin_client.post("/api/platform/v1/model-profiles/", {
        "provider": provider_id, "name": "Test model", "model_code": "gpt-4o-mini",
        "enabled": True, "input_price_per_million": "0.200000",
        "output_price_per_million": "0.800000", "max_output_tokens": 512,
    }, format="json")
    assert profile.status_code == 201, profile.data
    assert admin_client.get("/api/platform/v1/model-profiles/").status_code == 200
    assert staff_client.get("/api/platform/v1/model-profiles/").status_code == 403
    assert admin_client.patch(f"/api/platform/v1/model-profiles/{profile.data['data']['id']}/", {
        "input_price_per_million": "-1"
    }, format="json").status_code == 400


@pytest.mark.django_db
def test_secret_environment_resolution_is_restricted(monkeypatch):
    assert validate_secret_ref("env:EAH_MODEL_KEY_MAIN")
    assert not validate_secret_ref("env:DJANGO_SECRET_KEY")
    assert not validate_secret_ref("sk-not-a-reference")
    monkeypatch.setenv("EAH_MODEL_KEY_MAIN", "dummy-test-value")
    assert resolve_secret("env:EAH_MODEL_KEY_MAIN") == "dummy-test-value"
    assert resolve_secret("env:DJANGO_SECRET_KEY") is None


@pytest.mark.django_db
def test_disabled_model_is_rejected_before_tool_execution(ready):
    run = new_run(ready, key="disable-late")
    profile = ready[1].model_profile
    profile.enabled = False
    profile.save(update_fields=["enabled"])
    with patch("agent_runtime.engine.invoke_read_tool") as invoke:
        execute_agent_run.apply(args=[str(run.pk)], throw=True)
        invoke.assert_not_called()
    run.refresh_from_db()
    assert run.status == "FAILED"
    assert run.error_code == "MODEL_UNAVAILABLE"


@pytest.mark.django_db
def test_cancel_and_usage_endpoints_enforce_owner_scope(ready, users, django_user_model):
    run = new_run(ready, key="owner-scope")
    owner_client = APIClient()
    owner_client.force_authenticate(user=ready[3])
    other = django_user_model.objects.create_user(username="p2a-unrelated", password="test", name="Other")
    other_client = APIClient()
    other_client.force_authenticate(user=other)
    cancel_url = "/api/platform/v1/runs/{}/cancel/".format(run.pk)
    usage_url = "/api/platform/v1/runs/{}/usage/".format(run.pk)
    assert other_client.post(cancel_url).status_code == 404
    assert other_client.get(usage_url).status_code == 404
    assert owner_client.get(usage_url).data["data"] is None
    assert owner_client.post(cancel_url).status_code == 200
    run.refresh_from_db()
    assert run.status == "CANCELLED"
