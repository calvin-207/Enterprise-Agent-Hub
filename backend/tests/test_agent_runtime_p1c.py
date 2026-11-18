"""P1-C integration and safety tests. All tests run without external keys."""
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone

from agent_catalog.models import Agent, AgentVersion, AgentAccessGrant, ToolGrant
from agent_runtime.models import AgentRun
from agent_runtime.services import start_run
from agent_runtime.tasks import execute_agent_run
from model_gateway.models import ModelProfile
from tool_gateway.models import ToolDefinition
from tool_gateway.executor import ToolDenied, ToolInputError, invoke_read_tool
from agent_runtime.adapter import make_adapter, ModelUnavailable


@pytest.fixture
def setup_agent(db, django_user_model):
    owner = django_user_model.objects.create_superuser(
        username="p1c-owner", password="StrongPass!2026", name="P1C Owner"
    )
    user = django_user_model.objects.create_user(
        username="p1c-user", password="StrongPass!2026", name="P1C User"
    )
    call_command("bootstrap_mock_catalog")
    agent = Agent.objects.create(code="p1c-sales", name="销售分析", owner=owner)
    version = AgentVersion.objects.create(
        agent=agent, version_number=1, system_prompt="Analyze synthetic sales",
        model_profile=ModelProfile.objects.get(model_code="mock-small"), created_by=owner,
    )
    tool = ToolDefinition.objects.get(code="mock_sales_summary")
    ToolGrant.objects.create(version=version, tool=tool)
    from agent_catalog.services import publish_version
    publish_version(agent, version.pk)
    agent.refresh_from_db()
    version.refresh_from_db()
    AgentAccessGrant.objects.create(agent=agent, user=user, capability="run")
    return agent, version, user, tool


def make_run(setup_agent, *, message="分析本月销售", key="p1c"):
    agent, version, user, tool = setup_agent
    run, _ = start_run(actor=user, agent=agent, payload={"message": message},
                       idempotency_key=key)
    return run


@pytest.mark.django_db
def test_mock_agent_full_loop_persists_evidence_events(setup_agent):
    run = make_run(setup_agent)
    execute_agent_run.apply(args=[str(run.pk)], throw=True)
    run.refresh_from_db()
    assert run.status == AgentRun.Status.SUCCEEDED
    assert run.result["mock"] is True
    assert "销售额" in run.result["answer"]
    assert run.result["evidence"] == ["synthetic:mock_sales_summary"]
    assert list(run.steps.values_list("kind", flat=True)) == ["DISPATCH", "TOOL_READ", "MODEL_CALL"]
    assert list(run.events.values_list("kind", flat=True)) == [
        "run.queued", "run.started", "run.step_completed", "run.step_completed", "run.completed"
    ]
    assert "sk-" not in str(run.result)
    assert "sk-" not in str(list(run.steps.values_list("details", flat=True)))


@pytest.mark.django_db
def test_tool_revoked_after_run_creation_is_denied(setup_agent):
    agent, version, user, tool = setup_agent
    run = make_run(setup_agent)
    ToolGrant.objects.filter(version=version, tool=tool).update(enabled=False)
    execute_agent_run.apply(args=[str(run.pk)], throw=True)
    run.refresh_from_db()
    assert run.status == AgentRun.Status.FAILED
    assert run.error_code == "TOOL_PERMISSION_DENIED"
    assert run.result is None


@pytest.mark.django_db
def test_user_access_revoked_after_queue_blocks_tool(setup_agent):
    agent, version, user, tool = setup_agent
    run = make_run(setup_agent)
    AgentAccessGrant.objects.filter(agent=agent, user=user).delete()
    execute_agent_run.apply(args=[str(run.pk)], throw=True)
    run.refresh_from_db()
    assert run.status == AgentRun.Status.FAILED
    assert run.error_code == "TOOL_PERMISSION_DENIED"


@pytest.mark.django_db
def test_only_allowlisted_tool_and_parameters(setup_agent):
    agent, version, user, tool = setup_agent
    with pytest.raises(ToolDenied):
        invoke_read_tool(version=version, actor=user, code="shell", arguments={})
    with pytest.raises(ToolInputError):
        invoke_read_tool(version=version, actor=user, code="mock_sales_summary", arguments={"sql": "DROP TABLE"})
    with pytest.raises(ToolInputError):
        invoke_read_tool(version=version, actor=user, code="mock_sales_summary", arguments={"month": "2026-11"})
    result = invoke_read_tool(version=version, actor=user, code="mock_sales_summary", arguments={"month": "2026-10"})
    assert result["total"] == 115000
    assert result["change_pct"] == -8.0
    assert result["source"].startswith("synthetic:")


@pytest.mark.django_db
def test_timeout_is_recorded_without_invoking_gateway(setup_agent):
    run = make_run(setup_agent)
    AgentRun.objects.filter(pk=run.pk).update(deadline_at=timezone.now() - timedelta(seconds=5))
    with patch("agent_runtime.engine.invoke_read_tool") as tool:
        execute_agent_run.apply(args=[str(run.pk)], throw=True)
        tool.assert_not_called()
    run.refresh_from_db()
    assert run.status == "FAILED"
    assert run.error_code == "RUN_BUDGET_EXCEEDED"


@pytest.mark.django_db
def test_invalid_message_fails_cleanly(setup_agent):
    run = make_run(setup_agent, message="   ")
    execute_agent_run.apply(args=[str(run.pk)], throw=True)
    run.refresh_from_db()
    assert run.status == "FAILED"
    assert run.error_code == "INVALID_INPUT"


@pytest.mark.django_db
def test_sdk_adapter_never_uses_mock_provider_as_live(setup_agent, monkeypatch):
    agent, version, user, tool = setup_agent
    assert make_adapter(version).__class__.__name__ == "MockRuntimeAdapter"
    version.model_profile.provider.adapter_type = "untrusted-provider"
    with pytest.raises(ModelUnavailable):
        make_adapter(version)


@pytest.mark.django_db
def test_live_sdk_import_is_not_shadowed_by_django_catalog(setup_agent, monkeypatch):
    """Verify SDK namespace after moving Django app to agent_catalog."""
    from agents import Agent as SDKAgent, Runner
    assert callable(Runner.run_sync)
    assert SDKAgent.__module__.startswith("agents.")
    from agent_catalog.models import Agent as DatabaseAgent
    assert SDKAgent is not DatabaseAgent


@pytest.mark.django_db
def test_openai_adapter_uses_real_sdk_boundary_without_network(setup_agent, monkeypatch):
    from types import SimpleNamespace
    from agent_runtime.adapter import OpenAIAgentsAdapter
    from agents import Runner

    agent, version, user, tool = setup_agent
    version.model_profile.provider.adapter_type = "openai"
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-placeholder-not-a-real-key")
    seen = {}

    def fake_run(sdk_agent, prompt, **kwargs):
        seen["model"] = sdk_agent.model
        seen["prompt"] = prompt
        seen["max_turns"] = kwargs["max_turns"]
        return SimpleNamespace(final_output="模拟数据分析完成")

    monkeypatch.setattr(Runner, "run_sync", fake_run)
    result = OpenAIAgentsAdapter().run(
        version=version, actor=user, message="分析月度销售",
        on_tool=lambda *args, **kwargs: {},
        check_budget=lambda: None,
    )
    assert result["mock"] is False
    assert result["answer"] == "模拟数据分析完成"
    assert seen["max_turns"] == 4
    assert seen["model"] == "mock-small"


@pytest.mark.django_db
def test_live_adapter_requires_worker_key(setup_agent, monkeypatch):
    from agent_runtime.adapter import OpenAIAgentsAdapter
    agent, version, user, tool = setup_agent
    version.model_profile.provider.adapter_type = "openai"
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ModelUnavailable):
        OpenAIAgentsAdapter().run(
            version=version, actor=user, message="分析",
            on_tool=lambda *args, **kwargs: {},
            check_budget=lambda: None,
        )
