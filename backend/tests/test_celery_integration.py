"""Celery integration tests that do not require a running Redis broker."""
from django.conf import settings
from celery import current_app

from main.celery import app as celery_app
from system.tasks import check_database, ping


def test_celery_loads_django_and_json_transport():
    assert celery_app.main == "enterprise_agent_hub"
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.result_serializer == "json"
    assert celery_app.conf.accept_content == ["json"]
    # 默认队列携带环境标签（hub-<env>），实现多环境物理隔离。
    assert celery_app.conf.task_default_queue == f"hub-{settings.CELERY_ENV_TAG}"
    assert celery_app.conf.task_time_limit == 300
    assert celery_app.conf.task_soft_time_limit == 270
    assert celery_app.conf.worker_prefetch_multiplier == 1
    assert celery_app.conf.broker_url.endswith("/3")
    assert celery_app.conf.result_backend.endswith("/4")


def test_worker_ping_executes_locally_without_redis():
    result = ping.apply(throw=True)
    assert result.successful()
    data = result.get()
    assert data["status"] == "ok"
    assert data["service"] == "enterprise-agent-hub"
    assert "timestamp" in data


def test_database_healthcheck_executes_in_tests(db):
    result = check_database.apply(throw=True)
    assert result.successful()


def test_worker_tasks_are_registered():
    celery_app.loader.import_default_modules()
    assert "system.ping" in celery_app.tasks
    assert "system.check_database" in celery_app.tasks
