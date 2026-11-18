"""Agent definitions, immutable published versions and explicit permissions."""
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Agent(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        ACTIVE = "active", "已发布"
        DISABLED = "disabled", "已停用"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=500, blank=True, default="")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="owned_agents")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.code


class AgentVersion(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        PUBLISHED = "published", "已发布"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    system_prompt = models.TextField(max_length=20000)
    model_profile = models.ForeignKey("model_gateway.ModelProfile", on_delete=models.PROTECT, related_name="agent_versions")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="authored_agent_versions")
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("agent", "version_number"), name="eah_unique_agent_version"),
        ]
        ordering = ("-version_number",)

    def save(self, *args, **kwargs):
        # Never allow updating fields on an already published row via ORM.save().
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values("status").first()
            if previous and previous["status"] == self.Status.PUBLISHED:
                raise ValidationError("已发布的 AgentVersion 不允许修改；请创建新版本")
        super().save(*args, **kwargs)


class AgentAccessGrant(models.Model):
    class Capability(models.TextChoices):
        RUN = "run", "运行"
        MANAGE = "manage", "管理"

    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="access_grants")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="agent_access_grants")
    capability = models.CharField(max_length=12, choices=Capability.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("agent", "user", "capability"), name="eah_unique_agent_user_capability"),
        ]


class ToolGrant(models.Model):
    version = models.ForeignKey(AgentVersion, on_delete=models.CASCADE, related_name="tool_grants")
    tool = models.ForeignKey("tool_gateway.ToolDefinition", on_delete=models.PROTECT, related_name="agent_grants")
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("version", "tool"), name="eah_unique_version_tool")]

    def save(self, *args, **kwargs):
        if self.version.status == AgentVersion.Status.PUBLISHED:
            # Safe revocation is allowed; adding/re-enabling a grant is not.
            previous = type(self).objects.filter(pk=self.pk).values("enabled").first()
            if not previous or not previous["enabled"] or self.enabled:
                raise ValidationError("已发布版本仅允许撤销已有工具权限，不允许新增或恢复")
        super().save(*args, **kwargs)
