"""P1-B worker verifies dispatch and persistence, NOT an LLM/Agent Loop."""
import logging
import uuid

from celery import shared_task
from agent_runtime.models import AgentRun
from agent_runtime.services import claim_run, finish_run

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
    # P1-C must replace this explicit failure with the real SDK RuntimeAdapter.
    # Claiming SUCCESS here would incorrectly report a completed Agent analysis.
    finish_run(
        run_id, lease, status=AgentRun.Status.FAILED,
        error_code="RUNTIME_NOT_IMPLEMENTED",
    )
    logger.info("AgentRun %s safely rejected: RuntimeAdapter not installed", run_id)
