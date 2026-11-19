"""Single source of the deployed code version.

Order of precedence:
1. HUB_CODE_VERSION environment variable (set explicitly in production builds);
2. git short hash of the checkout (local development and CI);
3. contents of backend/VERSION (release artifacts that strip .git);
4. "unknown" (version checks are then skipped for unstamped messages).

The value is stamped onto every Celery message and verified by the worker so
that a stale worker (code updated but process not restarted) never consumes
tasks produced by a newer API/Beat.

注意：本模块在 settings.py 加载期间被调用，绝不能访问 django.conf.settings。
"""
import os
import subprocess
from functools import lru_cache
from pathlib import Path

# backend/ 目录（main/version.py 的上一级）
BASE_DIR = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def get_code_version() -> str:
    override = os.environ.get("HUB_CODE_VERSION", "").strip()
    if override:
        return override[:40]

    git = _git_short_hash()
    if git:
        return git

    version_file = BASE_DIR / "VERSION"
    try:
        content = version_file.read_text(encoding="utf-8").strip()
    except OSError:
        content = ""
    if content:
        return content[:40]
    return "unknown"


def _git_short_hash() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=BASE_DIR, capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()[:12]
