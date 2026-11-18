"""Safe, recoverable Outbox sender; run via a separate process."""
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from agent_runtime.models import DispatchOutbox
from agent_runtime.tasks import execute_agent_run


def dispatch_pending(limit=50):
    now = timezone.now()
    sent = 0
    due = DispatchOutbox.objects.filter(
        Q(status=DispatchOutbox.Status.PENDING)
        | Q(status=DispatchOutbox.Status.SENDING, lease_until__lt=now),
    ).filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
    for pk in due.order_by("id").values_list("pk", flat=True)[:limit]:
        # Conditional claim: two dispatchers cannot both own the same row concurrently.
        claimed = DispatchOutbox.objects.filter(pk=pk).filter(
            Q(status=DispatchOutbox.Status.PENDING)
            | Q(status=DispatchOutbox.Status.SENDING, lease_until__lt=now)
        ).update(status=DispatchOutbox.Status.SENDING, lease_until=now + timedelta(seconds=60))
        if not claimed:
            continue
        record = DispatchOutbox.objects.get(pk=pk)
        try:
            execute_agent_run.apply_async(
                args=[str(record.run_id)],
                task_id=str(record.run_id), queue="default",
            )
        except Exception:
            # Message may already have arrived despite a network timeout.
            # Re-delivery is safe: Worker claims AgentRun with DB CAS.
            attempt = record.attempts + 1
            backoff = min(300, 2 ** min(attempt, 8))
            DispatchOutbox.objects.filter(pk=pk, status=DispatchOutbox.Status.SENDING).update(
                status=DispatchOutbox.Status.PENDING, attempts=attempt,
                lease_until=None, next_attempt_at=timezone.now() + timedelta(seconds=backoff),
                last_error="BROKER_UNAVAILABLE",
            )
        else:
            DispatchOutbox.objects.filter(pk=pk, status=DispatchOutbox.Status.SENDING).update(
                status=DispatchOutbox.Status.SENT, sent_at=timezone.now(),
                lease_until=None, attempts=record.attempts + 1, last_error="",
            )
            sent += 1
    return sent
