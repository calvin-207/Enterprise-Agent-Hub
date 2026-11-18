from rest_framework import serializers

from agents.models import Agent, AgentAccessGrant, AgentVersion, ToolGrant
from model_gateway.models import ModelProfile
from tool_gateway.models import ToolDefinition


class AgentSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)

    class Meta:
        model = Agent
        fields = ("id", "code", "name", "description", "status", "owner_username", "created_at", "updated_at")
        read_only_fields = ("id", "status", "owner_username", "created_at", "updated_at")


class AgentVersionSerializer(serializers.ModelSerializer):
    model_profile = serializers.PrimaryKeyRelatedField(queryset=ModelProfile.objects.all())
    tool_ids = serializers.PrimaryKeyRelatedField(
        source="tools", queryset=ToolDefinition.objects.all(), many=True, write_only=True,
        required=False,
    )
    tools = serializers.SerializerMethodField()

    class Meta:
        model = AgentVersion
        fields = (
            "id", "agent", "version_number", "status", "system_prompt",
            "model_profile", "tool_ids", "tools", "created_at", "published_at",
        )
        read_only_fields = ("id", "agent", "version_number", "status", "created_at", "published_at")

    def get_tools(self, obj):
        return [
            {"id": grant.tool_id, "code": grant.tool.code, "enabled": grant.enabled}
            for grant in obj.tool_grants.select_related("tool").all()
        ]

    def validate(self, attrs):
        if self.instance and self.instance.status == AgentVersion.Status.PUBLISHED:
            raise serializers.ValidationError("已发布版本不可编辑；请创建新版本")
        return attrs


class ModelProfileSerializer(serializers.ModelSerializer):
    provider_code = serializers.CharField(source="provider.code", read_only=True)

    class Meta:
        model = ModelProfile
        fields = ("id", "name", "model_code", "enabled", "provider", "provider_code")
        read_only_fields = fields


class ToolCatalogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ToolDefinition
        fields = ("id", "code", "name", "kind", "version", "input_schema", "output_schema", "enabled")
        read_only_fields = fields


class AgentAccessSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentAccessGrant
        fields = ("id", "agent", "user", "capability", "created_at")
        read_only_fields = ("id", "created_at")
