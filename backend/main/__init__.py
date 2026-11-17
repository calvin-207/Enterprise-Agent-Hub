import config

if config.DATABASE_TYPE == "MYSQL":
    import pymysql

    pymysql.install_as_MySQLdb()

# Bind shared_task to this Django-configured Celery app.
from .celery import app as celery_app

__all__ = ("celery_app",)
