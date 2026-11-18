"""Run a dedicated dispatcher process; --once is useful for smoke tests."""
import time

from django.core.management.base import BaseCommand
from agent_runtime.dispatcher import dispatch_pending
from agent_runtime.services import expire_abandoned_runs


class Command(BaseCommand):
    help = "可靠派发待执行 AgentRun，支持 --once 或长期循环"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--interval", type=float, default=2.0)

    def handle(self, *args, **options):
        interval = options["interval"]
        if interval < 0.1:
            raise ValueError("interval must be >= 0.1")
        while True:
            sent = dispatch_pending()
            expired = expire_abandoned_runs()
            if sent or expired:
                self.stdout.write(f"dispatched={sent}, expired={expired}")
            if options["once"]:
                return
            time.sleep(interval)
