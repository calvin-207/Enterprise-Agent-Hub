"""All Agent publishing and access mutations are centralized here."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from agents.models import Agent, AgentAccessGrant, AgentVersion, ToolGrant
from tool_gateway.models import ToolDefinition


def is_platform_admin(user):
    return bool(user and user.is_authenticated and user.is_active
                and user.is_staff and user.is_superuser
                and not getattr(user, "is_delete", False))


def is_granted(user, agent, capability="run"):
    """Re-evaluate grants against the database; never infer tool access from menus."""
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if getattr(user, "is_delete", False):
        return False
    if is_platform_admin(user):
        return True
    return AgentAccessGrant.objects.filter(
        agent=agent, user=user, capability=capability,
    ).exists()


def allowed_tool_ids(version, user):
    """Runtime must call this again *at each tool invocation* in P1-C."""
    if version.status != AgentVersion.Status.PUBLISHED:
        return []
    if version.agent.status != Agent.Status.ACTIVE or not is_granted(user, version.agent):
        return []
    if not version.model_profile.enabled or not version.model_profile.provider.enabled:
        return []
    return list(ToolGrant.objects.filter(
        version=version, enabled=True, tool__enabled=True,
        tool__kind=ToolDefinition.Kind.MOCK_READ,
    ).values_list("tool_id", flat=True))


@transaction.atomic
def publish_version(agent, version_id):
    agent = Agent.objects.select_for_update().get(pk=agent.pk)
    version = AgentVersion.objects.select_related("model_profile__provider").get(
        pk=version_id, agent=agent,
    )
    if version.status != AgentVersion.Status.DRAFT:
        raise ValidationError("该版本已经发布")
    if agent.status == Agent.Status.DISABLED:
        raise ValidationError("已停用 Agent 不允许发布")
    if not version.system_prompt.strip():
        raise ValidationError("系统提示词不能为空")
    profile = version.model_profile
    if not profile.enabled or not profile.provider.enabled:
        raise ValidationError("模型提供商和模型配置必须启用")
    grants = list(version.tool_grants.select_related("tool").filter(enabled=True))
    if not grants or any(
        not g.tool.enabled or g.tool.kind != ToolDefinition.Kind.MOCK_READ
        for g in grants
    ):
        raise ValidationError("发布版本必须配置至少一个已启用的只读工具")

    # Use queryset.update for the controlled one-way draft -> published transition.
    updated = AgentVersion.objects.filter(
        pk=version.pk, status=AgentVersion.Status.DRAFT,
    ).update(status=AgentVersion.Status.PUBLISHED, published_at=timezone.now())
    if updated != 1:
        raise ValidationError("版本发布冲突")
    Agent.objects.filter(pk=agent.pk).update(status=Agent.Status.ACTIVE)
    return AgentVersion.objects.get(pk=version.pk)


@transaction.atomic
def create_version(agent, actor, prompt, model_profile, tools):
    if agent.status == Agent.Status.DISABLED:
        raise ValidationError("Agent 已停用")
    Agent.objects.select_for_update().get(pk=agent.pk)
    next_number = (agent.versions.order_by("-version_number")
                   .values_list("version_number", flat=True).first() or 0) + 1
    version = AgentVersion.objects.create(
        agent=agent, version_number=next_number, system_prompt=prompt,
        model_profile=model_profile, created_by=actor,
    )
    for tool in tools:
        ToolGrant.objects.create(version=version, tool=tool)
    return version


@transaction.atomic
def revoke_tool(version, tool_id):
    """An enabled grant may be disabled after publication, never re-enabled."""
    count = ToolGrant.objects.filter(
        version=version, tool_id=tool_id, enabled=True,
    ).update(enabled=False)
    return count
