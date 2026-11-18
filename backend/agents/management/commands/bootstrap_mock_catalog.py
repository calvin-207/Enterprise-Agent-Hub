"""Explicitly opt in to simulated model/tool metadata for P1-A demos."""
from django.core.management.base import BaseCommand

from model_gateway.models import ModelProvider, ModelProfile
from tool_gateway.models import ToolDefinition


class Command(BaseCommand):
    help = "创建不含真实凭据的 P1-A 模拟 ModelProfile 和只读工具"

    def handle(self, *args, **options):
        provider, _ = ModelProvider.objects.get_or_create(
            code="mock", defaults={"name": "Mock Model Provider", "adapter_type": "mock", "enabled": True},
        )
        if provider.adapter_type != "mock":
            raise ValueError("mock provider code 已被非模拟适配器占用")
        profile, _ = ModelProfile.objects.get_or_create(
            provider=provider, model_code="mock-small",
            defaults={"name": "Mock Small", "enabled": True},
        )
        tool, _ = ToolDefinition.objects.get_or_create(
            code="mock_sales_summary",
            defaults={
                "name": "模拟销售额分析（只读）",
                "kind": ToolDefinition.Kind.MOCK_READ,
                "enabled": True,
                "input_schema": {"type": "object", "properties": {"month": {"type": "string"}}},
                "output_schema": {"type": "object"},
            },
        )
        self.stdout.write(self.style.SUCCESS(
            f"模拟目录已就绪：provider={provider.pk}, profile={profile.pk}, tool={tool.pk}"
        ))
