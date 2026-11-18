"""Run creation and append-only transitions. Database is the source of truth."""
import hashlib
import json
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Max, F
from django.utils import timezone

from agent_catalog.models import Agent, AgentVersion
from agent_catalog.services import allowed_tool_ids, is_granted
from agent_runtime.models import AgentRun, RunEvent, RunStep, DispatchOutbox


class RunCancelled(Exception):
    pass


class RunRejected(Exception):
    def __init__(self, message, http_status=400, code="RUN_REJECTED"):
        self.message, self.http_status, self.code = message, http_status, code
        super().__init__(message)


def canonical_hash(value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def snapshot_for(version, actor):
    return {
        "agent_version": str(version.pk),
        "prompt_sha256": hashlib.sha256(version.system_prompt.encode("utf-8")).hexdigest(),
        "model_profile_id": version.model_profile_id,
        "model_code": version.model_profile.model_code,
        "tool_ids": allowed_tool_ids(version, actor),
    }


def start_run(*, actor, agent, payload, idempotency_key, deadline_seconds=120):
    if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 120:
        raise RunRejected("必须提交有效的 Idempotency-Key", 400, "IDEMPOTENCY_KEY_REQUIRED")
    if not isinstance(payload, dict) or not payload:
        raise RunRejected("input 必须是非空 JSON 对象")
    if not isinstance(deadline_seconds, int) or isinstance(deadline_seconds, bool) or not 1 <= deadline_seconds <= 270:
        raise RunRejected("deadline_seconds 必须在 1 到 270 秒之间")
    if len(json.dumps(payload, ensure_ascii=False)) > 16000:
        raise RunRejected("输入超过大小限制")
    # The key scope is the authenticated actor, not the requested agent.
    digest = canonical_hash({"agent": str(agent.pk), "input": payload, "deadline": deadline_seconds})
    existing = AgentRun.objects.filter(requested_by=actor, idempotency_key=idempotency_key).first()
    if existing:
        if existing.input_digest != digest:
            raise RunRejected("相同幂等键不能用于不同请求", 409, "IDEMPOTENCY_CONFLICT")
        return existing, False

    if agent.status != Agent.Status.ACTIVE or not is_granted(actor, agent):
        raise RunRejected("没有运行此 Agent 的权限", 403, "FORBIDDEN")
    version = AgentVersion.objects.select_related("agent", "model_profile__provider").filter(
        agent=agent, status=AgentVersion.Status.PUBLISHED,
    ).order_by("-version_number").first()
    if not version:
        raise RunRejected("Agent 尚未发布", 409, "AGENT_VERSION_NOT_PUBLISHED")
    snapshot = snapshot_for(version, actor)
    if not snapshot["tool_ids"] or not version.model_profile.enabled or not version.model_profile.provider.enabled:
        raise RunRejected("模型或工具当前不可用", 409, "AGENT_CONFIGURATION_UNAVAILABLE")

    try:
        with transaction.atomic():
            run = AgentRun.objects.create(
                agent=agent, version=version, requested_by=actor,
                input=payload, input_digest=digest, idempotency_key=idempotency_key,
                version_snapshot=snapshot,
                deadline_at=timezone.now() + timedelta(seconds=deadline_seconds),
            )
            RunEvent.objects.create(run=run, sequence=1, kind="run.queued", payload={"status": "QUEUED"})
            DispatchOutbox.objects.create(run=run)
            return run, True
    except IntegrityError:
        # Concurrent identical request raced at the database unique constraint.
        run = AgentRun.objects.get(requested_by=actor, idempotency_key=idempotency_key)
        if run.input_digest != digest:
            raise RunRejected("相同幂等键不能用于不同请求", 409, "IDEMPOTENCY_CONFLICT")
        return run, False


def claim_run(run_id, lease_token, lease_seconds=120):
    now = timezone.now()
    with transaction.atomic():
        candidate = AgentRun.objects.filter(pk=run_id, status=AgentRun.Status.QUEUED).first()
        if candidate is None:
            return False
        # SDK requests may block beyond 120s. Lease must cover the requested
        # deadline plus a small cleanup grace; Worker hard cap remains 300s.
        lease_end = now + timedelta(seconds=lease_seconds)
        if candidate.deadline_at:
            lease_end = max(lease_end, min(candidate.deadline_at + timedelta(seconds=15),
                                           now + timedelta(seconds=290)))
        updated = AgentRun.objects.filter(pk=run_id, status=AgentRun.Status.QUEUED).update(
            status=AgentRun.Status.RUNNING, status_version=2,
            lease_token=lease_token, lease_until=lease_end,
            started_at=now,
        )
        if updated:
            run = AgentRun.objects.get(pk=run_id)
            RunEvent.objects.create(run=run, sequence=2, kind="run.started", payload={"status": "RUNNING"})
            RunStep.objects.create(run=run, sequence=1, kind="DISPATCH", status="RUNNING", details={})
        return bool(updated)


def request_cancel(run_id):
    """Cooperative cancel. A running external request is not forcibly aborted."""
    with transaction.atomic():
        run = AgentRun.objects.select_for_update().get(pk=run_id)
        if run.status == AgentRun.Status.QUEUED:
            AgentRun.objects.filter(pk=run_id, status=AgentRun.Status.QUEUED).update(
                status=AgentRun.Status.CANCELLED, status_version=F("status_version") + 1,
                finished_at=timezone.now(),
            )
            DispatchOutbox.objects.filter(run=run, status__in=[
                DispatchOutbox.Status.PENDING, DispatchOutbox.Status.SENDING,
            ]).update(status=DispatchOutbox.Status.CANCELLED)
            seq = (run.events.aggregate(last=Max("sequence"))["last"] or 0) + 1
            RunEvent.objects.create(run=run, sequence=seq, kind="run.cancelled", payload={"status": "CANCELLED"})
        elif run.status == AgentRun.Status.RUNNING:
            AgentRun.objects.filter(pk=run_id, status=AgentRun.Status.RUNNING).update(
                status=AgentRun.Status.CANCEL_REQUESTED,
                status_version=F("status_version") + 1,
            )
            seq = (run.events.aggregate(last=Max("sequence"))["last"] or 0) + 1
            RunEvent.objects.create(run=run, sequence=seq, kind="run.cancel_requested",
                                    payload={"status": "CANCEL_REQUESTED"})
        run.refresh_from_db()
        return run


def finish_run(run_id, lease_token, *, status, error_code="", result=None):
    """Only the owning Worker can finish; cancellation wins against late output."""
    if status not in (AgentRun.Status.SUCCEEDED, AgentRun.Status.FAILED, AgentRun.Status.CANCELLED):
        raise ValueError("Invalid terminal status")
    with transaction.atomic():
        current = AgentRun.objects.select_for_update().filter(
            pk=run_id, lease_token=lease_token,
            status__in=(AgentRun.Status.RUNNING, AgentRun.Status.CANCEL_REQUESTED),
        ).first()
        if not current:
            return False
        if current.status == AgentRun.Status.CANCEL_REQUESTED:
            status, error_code, result = AgentRun.Status.CANCELLED, "", None
        AgentRun.objects.filter(pk=run_id, lease_token=lease_token).update(
            status=status, status_version=F("status_version") + 1,
            lease_token=None, lease_until=None,
            finished_at=timezone.now(), error_code=error_code, result=result,
        )
        RunStep.objects.filter(run_id=run_id, sequence=1).update(
            status=status,
            details={"error_code": error_code} if error_code else {"dispatch": "accepted"},
        )
        sequence = (current.events.aggregate(last=Max("sequence"))["last"] or 0) + 1
        kind = {
            AgentRun.Status.SUCCEEDED: "run.completed",
            AgentRun.Status.FAILED: "run.failed",
            AgentRun.Status.CANCELLED: "run.cancelled",
        }[status]
        RunEvent.objects.create(run_id=run_id, sequence=sequence, kind=kind,
                                payload={"status": status, "error_code": error_code})
        return True


def expire_abandoned_runs():
    """P1-B fail closed; resuming an unknown tool side effect needs P1-C checkpoints."""
    now = timezone.now()
    count = 0
    for run_id, token in AgentRun.objects.filter(
        status__in=(AgentRun.Status.RUNNING, AgentRun.Status.CANCEL_REQUESTED), lease_until__lt=now
    ).values_list("id", "lease_token")[:100]:
        if token and finish_run(
            run_id, token, status=AgentRun.Status.FAILED, error_code="WORKER_LEASE_EXPIRED"
        ):
            count += 1
    return count
