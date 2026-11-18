"""Provider adapters. Mock is deterministic/offline; OpenAI SDK is opt-in."""
from model_gateway.secrets import resolve_secret


class ModelUnavailable(Exception):
    code = "MODEL_UNAVAILABLE"


class RunBudgetExceeded(Exception):
    code = "RUN_BUDGET_EXCEEDED"


class InvalidModelOutput(Exception):
    code = "MODEL_OUTPUT_INVALID"


class MockRuntimeAdapter:
    """A deterministic two-step model/tool loop for integration tests and demos."""
    def run(self, *, version, actor, message, on_tool, check_budget):
        check_budget()
        month = "2026-09" if "9月" in message or "09" in message else "2026-10"
        evidence = on_tool("mock_sales_summary", {"month": month})
        check_budget()
        if evidence["previous_total"] is not None:
            answer = (
                f"模拟数据：{month} 销售额 {evidence['total']} 元，"
                f"较上月变化 {evidence['change_pct']}%，"
                f"渠道A为 {evidence['channel_a']} 元、渠道B为 {evidence['channel_b']} 元。"
                "这是演示数据，不能代表真实企业经营情况。"
            )
        else:
            answer = f"模拟数据：{month} 销售额 {evidence['total']} 元；无上月可比数据。"
        return {"answer": answer, "evidence": [evidence["source"]], "mock": True,
                "usage": {"input_tokens": 0, "output_tokens": 0}}


class OpenAIAgentsAdapter:
    """Real SDK runner. SDK controls LLM turns, Gateway remains tool authorization authority."""
    def run(self, *, version, actor, message, on_tool, check_budget):
        if version.model_profile.provider.adapter_type != "openai":
            raise ModelUnavailable("未启用受信任的 OpenAI Provider")
        provider_config = version.model_profile.provider
        key = resolve_secret(provider_config.secret_ref or "env:OPENAI_API_KEY")
        if not key:
            raise ModelUnavailable("Worker 缺少当前 Provider 的密钥")
        from agents import Agent as SDKAgent, Runner, RunConfig, OpenAIProvider, ModelSettings, function_tool

        @function_tool
        def mock_sales_summary(month: str = "2026-10") -> str:
            """Read synthetic monthly sales totals. month: 2026-09 or 2026-10."""
            import json
            check_budget()
            data = on_tool("mock_sales_summary", {"month": month})
            return json.dumps(data, ensure_ascii=False)

        check_budget()
        agent = SDKAgent(
            name=version.agent.name,
            instructions=version.system_prompt + "\n只允许使用提供的只读工具。严禁声称模拟数据是真实经营数据。",
            model=version.model_profile.model_code,
            model_settings=ModelSettings(max_tokens=version.model_profile.max_output_tokens),
            tools=[mock_sales_summary],
        )
        # SDK tracing defaults to transmitting model/tool content; disable it here.
        result = Runner.run_sync(
            agent, message, max_turns=4,
            run_config=RunConfig(tracing_disabled=True, model_provider=OpenAIProvider(api_key=key)),
        )
        check_budget()
        answer = result.final_output
        if not isinstance(answer, str) or not answer.strip():
            raise InvalidModelOutput("模型没有返回有效文本")
        usage = getattr(getattr(result, "context_wrapper", None), "usage", None)
        def valid_count(field):
            n = getattr(usage, field, None)
            return n if type(n) is int and 0 <= n <= 10**9 else None
        return {"answer": answer[:12000], "mock": False, "evidence": ["synthetic:mock_sales_summary"],
                "usage": {"input_tokens": valid_count("input_tokens"),
                          "output_tokens": valid_count("output_tokens")}}


def make_adapter(version):
    kind = version.model_profile.provider.adapter_type
    if kind == "mock":
        return MockRuntimeAdapter()
    if kind == "openai":
        return OpenAIAgentsAdapter()
    raise ModelUnavailable("该模型适配器尚未实现")
