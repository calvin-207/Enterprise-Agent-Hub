"""Small, safe built-in tasks that verify the automation infrastructure.

Business tasks should live in their owning Django app's tasks.py. Do not pass
secrets, model instances or large payloads through Celery messages.
"""
import logging

from celery import shared_task
from django.db import connection
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name="system.ping", ignore_result=False)
def ping():
    """Verify that a worker can execute a JSON-serializable task."""
    return {"status": "ok", "service": "enterprise-agent-hub", "timestamp": timezone.now().isoformat()}


@shared_task(name="system.check_database", ignore_result=True)
def check_database():
    """Optional scheduled DB connectivity probe; no business data is mutated."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        if cursor.fetchone()[0] != 1:
            raise RuntimeError("Database connectivity probe returned an unexpected value")
    logger.info("Celery scheduled database connectivity probe succeeded")
