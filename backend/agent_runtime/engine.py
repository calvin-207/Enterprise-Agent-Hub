"""P1-C orchestration: bounded read-only execution and durable checkpoints."""
import logging
from datetime import timedelta
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from agent_runtime.adapter import make_adapter, RunBudgetExceeded, ModelUnavailable
from model_gateway.models import ModelProfile
from agent_runtime.accounting import save_usage
from agent_runtime.services import RunCancelled
from agent_runtime.models import AgentRun, RunEvent, RunStep
from agent_runtime.services import finish_run
from tool_gateway.executor import invoke_read_tool

logger = logging.getLogger(__name__)
MAX_TOOLS = 5
MAX_STEPS = 12


def record_step(run_id, lease, kind, details):
    """Append a bounded, redacted event+step under Run lease ownership."""
    with transaction.atomic():
        run = AgentRun.objects.select_for_update().get(pk=run_id)
        if run.status != AgentRun.Status.RUNNING or run.lease_token != lease:
            raise RunBudgetExceeded("运行租约无效")
        if run.deadline_at and timezone.now() >= run.deadline_at:
            raise RunBudgetExceeded("Agent 运行超过截止时间")
        seq = (run.steps.aggregate(m=Max("sequence"))["m"] or 0) + 1
        if seq > MAX_STEPS:
            raise RunBudgetExceeded("超过最大执行步骤数")
        RunStep.objects.create(run=run, sequence=seq, kind=kind, status="SUCCEEDED", details=details)
        event_seq = (run.events.aggregate(m=Max("sequence"))["m"] or 0) + 1
        RunEvent.objects.create(run=run, sequence=event_seq, kind="run.step_completed",
                                payload={"step": seq, "kind": kind})
        return seq


def perform_run(run_id, lease):
    run = AgentRun.objects.select_related(
        "requested_by", "agent", "version__agent", "version__model_profile__provider"
    ).get(pk=run_id)
    version = run.version
    actor = run.requested_by
    if not isinstance(run.input, dict) or not isinstance(run.input.get("message"), str):
        raise ValueError("input.message 必须为字符串")
    message = run.input["message"].strip()
    if not message or len(message) > 4000:
        raise ValueError("输入消息为空或超过 4000 字符")
    calls = 0

    def check_budget():
        current = AgentRun.objects.only("status", "lease_token", "deadline_at").get(pk=run_id)
        if current.status == AgentRun.Status.CANCEL_REQUESTED and current.lease_token == lease:
            raise RunCancelled("任务已请求取消")
        if current.status != AgentRun.Status.RUNNING or current.lease_token != lease:
            raise RunBudgetExceeded("任务租约已撤销")
        if current.deadline_at and timezone.now() >= current.deadline_at:
            raise RunBudgetExceeded("执行已超时")
        if not ModelProfile.objects.filter(pk=version.model_profile_id, enabled=True, provider__enabled=True).exists():
            raise ModelUnavailable("模型配置已停用")

    def on_tool(code, arguments):
        nonlocal calls
        check_budget()
        if calls >= MAX_TOOLS:
            raise RunBudgetExceeded("超过最大工具调用次数")
        calls += 1
        # Tool permission checked in Gateway against CURRENT DB grants every call.
        result = invoke_read_tool(version=version, actor=actor, code=code, arguments=arguments)
        record_step(run_id, lease, "TOOL_READ", {
            "tool": code, "source": result["source"], "month": result["month"],
            "call_number": calls,
        })
        return result

    check_budget()
    adapter = make_adapter(version)
    result = adapter.run(version=version, actor=actor, message=message,
                         on_tool=on_tool, check_budget=check_budget)
    check_budget()
    if not isinstance(result, dict) or not isinstance(result.get("answer"), str):
        raise ValueError("模型返回无效的结果")
    record_step(run_id, lease, "MODEL_CALL", {
        "adapter": version.model_profile.provider.adapter_type,
        "model": version.model_profile.model_code,
        "tool_calls": calls,
        "mock": result.get("mock", False),
        "usage": result.get("usage", {}),
    })
    save_usage(run, version, result.get("usage", {}))
    return result
