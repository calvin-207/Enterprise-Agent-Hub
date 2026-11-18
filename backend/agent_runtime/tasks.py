"""Celery execution of an allowlisted AgentRun. The DB remains authoritative."""
import logging
import uuid

from celery import shared_task
from agent_runtime.models import AgentRun
from agent_runtime.services import claim_run, finish_run
from agent_runtime.engine import perform_run

logger = logging.getLogger(__name__)


@shared_task(name="agent_runtime.execute", ignore_result=True)
def execute_agent_run(run_id):
    try:
        run_id = uuid.UUID(str(run_id))
    except (ValueError, TypeError, AttributeError):
        return
    lease = uuid.uuid4()
    if not claim_run(run_id, lease):
        return
    try:
        result = perform_run(run_id, lease)
    except Exception as exc:
        # Never log sensitive input or raw SDK/third-party exception messages.
        safe_codes = {
            "ToolDenied": "TOOL_PERMISSION_DENIED",
            "ToolInputError": "TOOL_INVALID_INPUT",
            "RunBudgetExceeded": "RUN_BUDGET_EXCEEDED",
            "ModelUnavailable": "MODEL_UNAVAILABLE",
            "InvalidModelOutput": "MODEL_OUTPUT_INVALID",
            "ValueError": "INVALID_INPUT",
        }
        error_code = safe_codes.get(type(exc).__name__, "RUNTIME_ERROR")
        logger.warning("AgentRun %s failed: %s", run_id, error_code)
        finish_run(run_id, lease, status=AgentRun.Status.FAILED, error_code=error_code)
    else:
        finish_run(run_id, lease, status=AgentRun.Status.SUCCEEDED, result=result)
