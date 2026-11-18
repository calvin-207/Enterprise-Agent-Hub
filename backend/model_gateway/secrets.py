"""Resolve credential references from the Worker environment, never from HTTP bodies.

Only env:OPENAI_API_KEY or env:EAH_MODEL_KEY_... are accepted.
The resolver intentionally does not support arbitrary filesystem paths/URLs.
"""
import os
import re

ALLOWED = re.compile(r"^(?:OPENAI_API_KEY|EAH_MODEL_KEY_[A-Z0-9_]{1,64})$")


def validate_secret_ref(value):
    if value == "":
        return True
    if not isinstance(value, str) or not value.startswith("env:"):
        return False
    return bool(ALLOWED.fullmatch(value[4:]))


def resolve_secret(ref):
    if not validate_secret_ref(ref) or not ref:
        return None
    return os.environ.get(ref[4:]) or None
