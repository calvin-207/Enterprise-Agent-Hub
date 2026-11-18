"""Superuser-only model/provider configuration. Secrets are NEVER accepted or returned."""
from decimal import Decimal, InvalidOperation
from django.db import IntegrityError, transaction
from django.core.exceptions import ImproperlyConfigured
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from agent_catalog.views import PlatformAPI
from agent_catalog.services import is_platform_admin
from rest_framework.exceptions import PermissionDenied
from model_gateway.models import ModelProvider, ModelProfile
from model_gateway.secrets import validate_secret_ref
from model_gateway.credentials import encrypt_api_key
from model_gateway.discovery import sync_models, ModelSyncError, safe_base_url

ALLOWED_PROVIDER_TYPES = {"mock", "openai", "openai_compatible"}


def ok(data, status=200):
    return Response({"code": 2000, "msg": "success", "data": data}, status=status)


def bad(message, status=400):
    return Response({"code": 400, "msg": str(message)}, status=status)


def provider_view(obj):
    return {"id": obj.pk, "code": obj.code, "name": obj.name,
            "adapter_type": obj.adapter_type, "secret_ref": obj.secret_ref,
            "enabled": obj.enabled, "base_url": obj.base_url,
            "has_stored_key": bool(obj.encrypted_api_key), "last_sync_at": obj.last_sync_at,
            "created_at": obj.created_at}


def profile_view(obj):
    return {"id": obj.pk, "provider": obj.provider_id, "name": obj.name,
            "model_code": obj.model_code, "enabled": obj.enabled,
            "input_price_per_million": str(obj.input_price_per_million),
            "output_price_per_million": str(obj.output_price_per_million),
            "max_output_tokens": obj.max_output_tokens,
            "is_default": obj.is_default, "source": obj.source,
            "last_seen_at": obj.last_seen_at}


def check_admin(request):
    if not is_platform_admin(request.user):
        raise PermissionDenied("需要平台管理员权限")


def check_keys(data, allowed):
    return isinstance(data, dict) and not (set(data) - set(allowed))


class ProviderConfigAPI(PlatformAPI):
    def get(self, request, provider_id=None):
        check_admin(request)
        if provider_id:
            return ok(provider_view(get_object_or_404(ModelProvider, pk=provider_id)))
        return ok([provider_view(p) for p in ModelProvider.objects.order_by("id")])

    def post(self, request, provider_id=None):
        check_admin(request)
        if provider_id is not None:
            return bad("Unsupported operation", 405)
        return self._save(request, None)

    def patch(self, request, provider_id=None):
        check_admin(request)
        return self._save(request, get_object_or_404(ModelProvider, pk=provider_id))

    def _save(self, request, instance):
        data = request.data
        fields = ("code", "name", "adapter_type", "secret_ref", "enabled", "base_url", "api_key", "clear_api_key")
        if not check_keys(data, fields):
            return bad("不支持此字段；禁止传入 API Key、URL 或其他敏感参数")
        kind = data.get("adapter_type", instance.adapter_type if instance else None)
        code = data.get("code", instance.code if instance else "")
        name = data.get("name", instance.name if instance else "")
        ref = data.get("secret_ref", instance.secret_ref if instance else "")
        enabled = data.get("enabled", instance.enabled if instance else False)
        base_url = data.get("base_url", instance.base_url if instance else "")
        api_key = data.get("api_key")
        clear_api_key = data.get("clear_api_key", False)
        from django.core.validators import validate_slug
        from django.core.exceptions import ValidationError
        try:
            validate_slug(code)
        except (ValidationError, TypeError):
            return bad("Provider code 不合法")
        if kind not in ALLOWED_PROVIDER_TYPES or not isinstance(name, str) or not 1 <= len(name) <= 120 or len(code) > 64:
            return bad("Provider 类型、名称或 code 不合法")
        if not isinstance(enabled, bool) or not validate_secret_ref(ref):
            return bad("只允许 env:OPENAI_API_KEY 或 env:EAH_MODEL_KEY_... 密钥引用")
        if kind == "openai" and enabled and not ref:
            return bad("启用真实模型时必须先配置 Secret Ref")
        if kind == "mock" and ref:
            return bad("Mock Provider 无需任何密钥引用")
        try:
            obj = instance or ModelProvider()
            obj.code, obj.name, obj.adapter_type = code, name, kind
            obj.secret_ref, obj.enabled = ref, enabled
            obj.save()
        except IntegrityError:
            return bad("Provider code 已存在", 409)
        return ok(provider_view(obj), 200 if instance else 201)


class ModelProfileConfigAPI(PlatformAPI):
    def get(self, request, profile_id=None):
        check_admin(request)
        if profile_id:
            return ok(profile_view(get_object_or_404(ModelProfile, pk=profile_id)))
        return ok([profile_view(p) for p in ModelProfile.objects.order_by("id")])

    def post(self, request, profile_id=None):
        check_admin(request)
        if profile_id is not None:
            return bad("Unsupported operation", 405)
        return self._save(request, None)

    def patch(self, request, profile_id=None):
        check_admin(request)
        return self._save(request, get_object_or_404(ModelProfile, pk=profile_id))

    def _save(self, request, instance):
        data = request.data
        allowed = ("provider", "name", "model_code", "enabled",
                   "input_price_per_million", "output_price_per_million", "max_output_tokens")
        if not check_keys(data, allowed):
            return bad("不支持的模型参数")
        try:
            provider_id = data.get("provider", instance.provider_id if instance else None)
            provider = ModelProvider.objects.get(pk=provider_id)
        except (ModelProvider.DoesNotExist, TypeError, ValueError):
            return bad("Provider 不存在")
        name = data.get("name", instance.name if instance else "")
        code = data.get("model_code", instance.model_code if instance else "")
        enabled = data.get("enabled", instance.enabled if instance else False)
        if not isinstance(name, str) or not 1 <= len(name) <= 120 or not isinstance(code, str) or not 1 <= len(code) <= 120 or not isinstance(enabled, bool):
            return bad("模型名称、标识或状态不合法")
        prices = []
        try:
            for field in ("input_price_per_million", "output_price_per_million"):
                value = Decimal(str(data.get(field, getattr(instance, field, 0))))
                if not value.is_finite() or not 0 <= value <= Decimal("99999999") or value.as_tuple().exponent < -6:
                    raise ValueError
                prices.append(value)
            max_tokens = data.get("max_output_tokens", instance.max_output_tokens if instance else 1024)
            if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or not 1 <= max_tokens <= 16384:
                raise ValueError
        except (ValueError, InvalidOperation, TypeError):
            return bad("价格或最大输出 Token 数不合法")
        try:
            obj = instance or ModelProfile()
            obj.provider, obj.name, obj.model_code, obj.enabled = provider, name, code, enabled
            obj.input_price_per_million, obj.output_price_per_million = prices
            obj.max_output_tokens = max_tokens
            obj.save()
        except IntegrityError:
            return bad("同一 Provider 下模型标识重复", 409)
        return ok(profile_view(obj), 200 if instance else 201)
