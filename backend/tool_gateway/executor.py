"""P1-C read-only Tool Gateway. No arbitrary Python/SQL/URL execution."""
from datetime import datetime
from django.utils import timezone

from agent_catalog.services import allowed_tool_ids
from tool_gateway.models import ToolDefinition


class ToolDenied(Exception):
    code = "TOOL_PERMISSION_DENIED"


class ToolInputError(Exception):
    code = "TOOL_INVALID_INPUT"


# Synthetic demo data only. Never interpret caller-provided SQL, URLs or Python.
MONTHLY_SALES = {
    "2026-09": {"total": 125000, "channel_a": 80000, "channel_b": 45000},
    "2026-10": {"total": 115000, "channel_a": 70000, "channel_b": 45000},
}


def invoke_read_tool(*, version, actor, code, arguments):
    if not isinstance(arguments, dict):
        raise ToolInputError("工具参数必须是对象")
    if version.status != "published" or version.agent.status != "active":
        raise ToolDenied("Agent 未发布或已停用")
    # This is rechecked on EVERY invocation, even after a run has started.
    tool = ToolDefinition.objects.filter(code=code, enabled=True, kind=ToolDefinition.Kind.MOCK_READ).first()
    if not tool or tool.id not in allowed_tool_ids(version, actor):
        raise ToolDenied("工具授权已撤销或当前用户无权访问")
    if tool.code != "mock_sales_summary":
        raise ToolDenied("未注册的只读工具")
    if set(arguments) - {"month"}:
        raise ToolInputError("包含未知参数")
    month = arguments.get("month", "2026-10")
    if not isinstance(month, str) or month not in MONTHLY_SALES:
        raise ToolInputError("月份不受支持，可选 2026-09 或 2026-10")
    current = MONTHLY_SALES[month]
    months = list(MONTHLY_SALES)
    previous = MONTHLY_SALES[months[months.index(month) - 1]] if months.index(month) > 0 else None
    delta = current["total"] - previous["total"] if previous else None
    return {
        "source": "synthetic:mock_sales_summary",
        "month": month,
        "currency": "CNY",
        "total": current["total"],
        "channel_a": current["channel_a"],
        "channel_b": current["channel_b"],
        "previous_total": previous["total"] if previous else None,
        "difference": delta,
        "change_pct": round(delta / previous["total"] * 100, 2) if previous else None,
    }
