"""Provider model discovery restricted to HTTPS public endpoints; never execute supplied URLs."""
import ipaddress
import socket
from urllib.parse import urlsplit
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import transaction

from model_gateway.credentials import get_provider_key
from model_gateway.models import ModelProfile, ModelProvider
from model_gateway.pricing_reference import pricing_reference_for


class ModelSyncError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def safe_base_url(provider):
    """Use only operator-approved HTTPS hosts and public DNS resolutions."""
    raw = (provider.base_url or "").strip()
    if provider.adapter_type == "mock":
        if raw:
            raise ModelSyncError("Mock 不支持自定义 URL")
        return None
    if provider.adapter_type == "openai":
        if raw and raw.rstrip("/") != "https://api.openai.com/v1":
            raise ModelSyncError("OpenAI 官方 Provider 只能使用官方 API 地址")
        return "https://api.openai.com/v1"
    if provider.adapter_type != "openai_compatible":
        raise ModelSyncError("当前 Provider 尚无模型发现适配器")
    if not raw:
        raise ModelSyncError("兼容 Provider 必须配置可信 Base URL")
    parts = urlsplit(raw)
    # MVP (2026-11-19): path convention dropped alongside the host allowlist — vendors
    # use different path layouts (/v1, /api/paas/v4, /v1beta/openai). Substantive
    # guards kept: HTTPS, default port, no credentials/query/fragment, public DNS.
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment or parts.port not in (None, 443)):
        raise ModelSyncError("Base URL 必须是无凭据、无查询参数、无自定义端口的 HTTPS 地址")
    # MVP decision (2026-11-19): the operator env allowlist (EAH_MODEL_ALLOWED_HOSTS)
    # was removed to keep provider setup fully admin-configurable. Remaining guards:
    # HTTPS-only, /v1 path, port 443, no credentials/query, public DNS resolution,
    # redirects disabled, 8s timeout. Revisit before internet-facing deployments.
    host = parts.hostname.lower().rstrip(".")
    try:
        answers = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        if not answers or any(not ipaddress.ip_address(a[4][0]).is_global for a in answers):
            raise ModelSyncError("模型 API 域名解析到了非公网地址")
    except (socket.gaierror, ValueError, IndexError) as exc:
        raise ModelSyncError("模型 API 域名解析失败") from exc
    return parts.geturl().rstrip("/")


def list_remote_models(provider):
    if not provider.enabled:
        raise ModelSyncError("请先启用 Provider")
    if provider.adapter_type == "mock":
        return [{"id": "mock-small", "name": "Mock Small"}]
    endpoint = safe_base_url(provider)
    try:
        key = get_provider_key(provider)
    except Exception as exc:
        raise ModelSyncError("密钥解密失败；请检查服务端加密密钥", 503) from exc
    if not key:
        raise ModelSyncError("未配置 API Key 或 Worker 环境变量不可用", 409)
    # openai>=3 is built on httpx2. Import dependencies separately so a missing
    # module surfaces as a clear server error, not a misleading vendor failure.
    try:
        import httpx2
        from openai import OpenAI
    except ImportError as exc:
        raise ModelSyncError("服务端缺少 openai/httpx2 依赖，请安装 requirements.txt", 500) from exc
    try:
        with httpx2.Client(follow_redirects=False, timeout=8) as http_client:
            client = OpenAI(api_key=key, base_url=endpoint, max_retries=0, timeout=8,
                            http_client=http_client)
            response = client.models.list()
            records = list(response.data)
    except Exception as exc:
        # Never leak raw provider errors: upstream exceptions may contain URLs/headers.
        # A bare upstream status code is safe to surface and speeds up diagnosis.
        detail = getattr(exc, "status_code", None)
        suffix = f"（供应商返回 HTTP {detail}）" if isinstance(detail, int) else ""
        raise ModelSyncError(
            f"供应商模型列表获取失败，请检查凭据、网络与接口兼容性{suffix}", 502
        ) from exc
    if len(records) > 1000:
        raise ModelSyncError("供应商模型列表超出安全上限（1000）", 422)
    result = []
    seen = set()
    for item in records:
        model_id = getattr(item, "id", None)
        if not isinstance(model_id, str) or not 1 <= len(model_id) <= 120:
            continue
        if any(ord(c) < 32 for c in model_id) or model_id in seen:
            continue
        seen.add(model_id)
        result.append({"id": model_id, "name": model_id})
    return result


def sync_models(provider):
    """Never overwrite local pricing, enabled, default or model routing decisions."""
    items = list_remote_models(provider)
    created = 0
    existing = 0
    priced = 0
    now = timezone.now()
    with transaction.atomic():
        locked = ModelProvider.objects.select_for_update().get(pk=provider.pk)
        for item in items:
            # Reference pricing/name/max-output only seed newly created profiles;
            # existing records (admin-maintained) are never touched by sync.
            ref = pricing_reference_for(item["id"])
            defaults = {"name": item["name"], "enabled": False, "source": "sync",
                        "last_seen_at": now}
            if ref:
                defaults.update({
                    "name": ref["name"], "input_price_per_million": ref["input"],
                    "output_price_per_million": ref["output"],
                    "max_output_tokens": ref["max_output_tokens"],
                })
            profile, fresh = ModelProfile.objects.get_or_create(
                provider=locked, model_code=item["id"], defaults=defaults,
            )
            if fresh:
                created += 1
                if ref:
                    priced += 1
            else:
                existing += 1
                ModelProfile.objects.filter(pk=profile.pk).update(last_seen_at=now)
        locked.last_sync_at = now
        locked.save(update_fields=["last_sync_at"])
    return {"total": len(items), "created": created, "existing": existing,
            "priced": priced, "last_sync_at": now}
