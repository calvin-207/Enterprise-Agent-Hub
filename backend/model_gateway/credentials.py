"""Encrypt provider API keys at rest with an independent deployment encryption key.

EAH_MODEL_ENCRYPTION_KEY is a Fernet key provisioned by Secret Manager.
Never derive this key from Django SECRET_KEY or expose API keys in responses.
"""
import os
from cryptography.fernet import Fernet, InvalidToken
from django.core.exceptions import ImproperlyConfigured

from model_gateway.secrets import resolve_secret


def _cipher():
    key = os.environ.get("EAH_MODEL_ENCRYPTION_KEY")
    if not key:
        raise ImproperlyConfigured("EAH_MODEL_ENCRYPTION_KEY must be provisioned for database credentials")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise ImproperlyConfigured("EAH_MODEL_ENCRYPTION_KEY is not a valid Fernet key") from exc


def encrypt_api_key(value):
    if not isinstance(value, str) or not 8 <= len(value) <= 4096 or value.strip() != value:
        raise ValueError("API Key format or length is invalid")
    return _cipher().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_api_key(value):
    try:
        return _cipher().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError) as exc:
        raise ImproperlyConfigured("Cannot decrypt model provider credentials") from exc


def get_provider_key(provider):
    if provider.encrypted_api_key:
        return decrypt_api_key(provider.encrypted_api_key)
    return resolve_secret(provider.secret_ref)
