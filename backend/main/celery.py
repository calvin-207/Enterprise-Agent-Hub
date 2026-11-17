"""Celery application used by Django API, workers, and beat.

Worker and beat must be separate processes. Redis is configured in settings.py.
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")

app = Celery("enterprise_agent_hub")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
