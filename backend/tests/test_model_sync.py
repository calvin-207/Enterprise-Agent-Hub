"""Model sync: safe credentials, opt-in configuration and non-destructive refresh."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from django.core.management import call_command
from rest_framework.test import APIClient

from model_gateway.models import ModelProvider, ModelProfile
from model_gateway.credentials import get_provider_key
from model_gateway.discovery import safe_base_url, ModelSyncError


@pytest.fixture
def admin(django_user_model):
    return django_user_model.objects.create_superuser(
        username="model-sync-admin", password="StrongPass!2026", name="Model Sync Admin"
    )


@pytest.fixture
def client(admin):
    c = APIClient()
    c.force_authenticate(user=admin)
    return c


@pytest.mark.django_db
def test_mock_sync_is_repeatable_and_preserves_local_settings(client):
    call_command("bootstrap_mock_catalog")
    provider = ModelProvider.objects.get(code="mock")
    profile = provider.profiles.get(model_code="mock-small")
    profile.enabled = True
    profile.name = "定制名称"
    profile.input_price_per_million = "1.500000"
    profile.save()
    url = f"/api/platform/v1/model-providers/{provider.pk}/sync/"
    first = client.post(url)
    assert first.status_code == 200, first.data
    assert first.data["data"]["total"] == 1
    assert first.data["data"]["created"] == 0
    second = client.post(url)
    assert second.status_code == 200, second.data
    assert provider.profiles.count() == 1
    profile.refresh_from_db()
    assert profile.enabled is True
    assert profile.name == "定制名称"
    assert str(profile.input_price_per_million) == "1.500000"
    assert profile.last_seen_at is not None


@pytest.mark.django_db
def test_remote_sync_imports_disabled_then_admin_can_select(client):
    p = ModelProvider.objects.create(
        code="remote-test", name="Remote", adapter_type="openai",
        enabled=True, secret_ref="env:EAH_MODEL_KEY_TEST"
    )
    mock_items = [{"id": "model-a", "name": "model-a"}, {"id": "model-b", "name": "model-b"}]
    with patch("model_gateway.discovery.list_remote_models", return_value=mock_items):
        reply = client.post(f"/api/platform/v1/model-providers/{p.pk}/sync/")
        assert reply.status_code == 200, reply.data
        assert reply.data["data"]["created"] == 2
        profiles = list(p.profiles.order_by("model_code"))
        assert [x.model_code for x in profiles] == ["model-a", "model-b"]
        assert all(not x.enabled and x.source == "sync" for x in profiles)
        first = profiles[0]
        changed = client.patch(f"/api/platform/v1/model-profiles/{first.pk}/", {
            "enabled": True, "is_default": True,
            "input_price_per_million": "0.123456",
            "output_price_per_million": "0.654321",
        }, format="json")
        assert changed.status_code == 200, changed.data
        assert changed.data["data"]["is_default"] is True
        assert client.post(f"/api/platform/v1/model-providers/{p.pk}/sync/").data["data"]["created"] == 0
        first.refresh_from_db()
        assert first.is_default and first.enabled
        assert str(first.input_price_per_million) == "0.123456"
        assert ModelProfile.objects.filter(is_default=True).count() == 1


@pytest.mark.django_db
def test_provider_key_encrypted_and_never_echoed(client, monkeypatch):
    monkeypatch.setenv("EAH_MODEL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    payload = {"code": "secure-provider", "name": "Secure Provider", "adapter_type": "openai",
               "api_key": "sk-test-not-a-real-credential", "enabled": True}
    response = client.post("/api/platform/v1/model-providers/", payload, format="json")
    assert response.status_code == 201, response.data
    p = ModelProvider.objects.get(code="secure-provider")
    assert p.encrypted_api_key != payload["api_key"]
    assert get_provider_key(p) == payload["api_key"]
    assert "sk-test-not-a-real-credential" not in str(response.data)
    assert "encrypted_api_key" not in str(response.data)
    assert response.data["data"]["has_stored_key"] is True
    update = client.patch(f"/api/platform/v1/model-providers/{p.pk}/", {
        "name": "Secure Provider Updated"
    }, format="json")
    assert update.status_code == 200, update.data
    p.refresh_from_db()
    assert get_provider_key(p) == payload["api_key"]
    assert client.patch(f"/api/platform/v1/model-providers/{p.pk}/", {
        "clear_api_key": True, "enabled": False
    }, format="json").status_code == 200
    p.refresh_from_db()
    assert not p.encrypted_api_key


@pytest.mark.django_db
def test_provider_key_requires_independent_encryption_key(client, monkeypatch):
    monkeypatch.delenv("EAH_MODEL_ENCRYPTION_KEY", raising=False)
    response = client.post("/api/platform/v1/model-providers/", {
        "code": "needs-encryption", "name": "Needs Encryption",
        "adapter_type": "openai", "api_key": "sk-test-credential", "enabled": True
    }, format="json")
    assert response.status_code == 503
    assert ModelProvider.objects.filter(code="needs-encryption").count() == 0


@pytest.mark.django_db
def test_sync_rejects_nonadmin_and_disabled(client, django_user_model):
    p = ModelProvider.objects.create(code="disabled-sync", name="disabled", adapter_type="openai")
    url = f"/api/platform/v1/model-providers/{p.pk}/sync/"
    user = django_user_model.objects.create_user(username="sync-basic", password="test", name="Basic")
    basic = APIClient()
    basic.force_authenticate(user=user)
    assert basic.post(url).status_code == 403
    assert APIClient().post(url).status_code == 401
    assert client.post(url).status_code == 400


@pytest.mark.django_db
def test_compatible_url_requires_operator_allowlist(client, monkeypatch):
    response = client.post("/api/platform/v1/model-providers/", {
        "code": "compatible", "name": "Third Party",
        "adapter_type": "openai_compatible", "base_url": "http://127.0.0.1:8000/v1",
    }, format="json")
    assert response.status_code == 400
    response = client.post("/api/platform/v1/model-providers/", {
        "code": "compatible", "name": "Third Party",
        "adapter_type": "openai_compatible", "base_url": "https://example.com/v1",
    }, format="json")
    assert response.status_code == 400
    monkeypatch.setenv("EAH_MODEL_ALLOWED_HOSTS", "example.com")
    with patch("model_gateway.discovery.socket.getaddrinfo", return_value=[
        (2, 1, 6, "", ("93.184.216.34", 443))
    ]):
        response = client.post("/api/platform/v1/model-providers/", {
            "code": "compatible", "name": "Third Party", "adapter_type": "openai_compatible",
            "base_url": "https://example.com/v1"
        }, format="json")
        assert response.status_code == 201, response.data
    with patch("model_gateway.discovery.socket.getaddrinfo", return_value=[
        (2, 1, 6, "", ("127.0.0.1", 443))
    ]):
        provider = ModelProvider.objects.get(code="compatible")
        with pytest.raises(ModelSyncError):
            safe_base_url(provider)


@pytest.mark.django_db
def test_remote_error_does_not_delete_or_disable_models(client):
    provider = ModelProvider.objects.create(code="unavailable", name="Unavailable", adapter_type="openai",
                                            enabled=True, secret_ref="env:EAH_MODEL_KEY_TEST")
    model = ModelProfile.objects.create(provider=provider, name="Existing", model_code="existing", enabled=True)
    with patch("model_gateway.discovery.list_remote_models", side_effect=ModelSyncError("上游不可用", 502)):
        res = client.post(f"/api/platform/v1/model-providers/{provider.pk}/sync/")
    assert res.status_code == 502
    model.refresh_from_db()
    assert model.enabled
    assert ModelProfile.objects.filter(provider=provider).count() == 1
