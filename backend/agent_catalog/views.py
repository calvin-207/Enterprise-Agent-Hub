"""P1-A configuration endpoints. No model/tool execution occurs here."""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated, PermissionDenied, NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView, exception_handler

from agent_catalog.models import Agent, AgentAccessGrant, AgentVersion, ToolGrant
from agent_catalog.serializers import (
    AgentSerializer, AgentVersionSerializer, AgentAccessSerializer,
    ModelProfileSerializer, ToolCatalogSerializer,
)
from agent_catalog.services import (
    create_version, is_granted, is_platform_admin, publish_version, revoke_tool,
)
from model_gateway.models import ModelProfile, ModelProvider
from tool_gateway.models import ToolDefinition
from utils.exception import format_validation_errors


def ok(data, http=status.HTTP_200_OK):
    return Response({"code": 2000, "msg": "success", "data": data}, status=http)


def bad(message, http=status.HTTP_400_BAD_REQUEST):
    # message 可能是 serializer.errors（ErrorDetail 嵌套结构），统一压平为可读文本
    return Response({"code": 400, "msg": format_validation_errors(message)}, status=http)


class PlatformAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def handle_exception(self, exc):
        # Existing legacy exception handler may convert 401/403 to HTTP 200.
        if isinstance(exc, (AuthenticationFailed, NotAuthenticated, PermissionDenied, NotFound, Http404, ValidationError)):
            response = exception_handler(exc, self.get_exception_handler_context())
            if response is not None:
                return response
        return super().handle_exception(exc)

    def admin_required(self, request):
        if not is_platform_admin(request.user):
            raise PermissionDenied("仅平台超级管理员可以修改 Agent 配置")


def accessible_agents(user):
    if is_platform_admin(user):
        return Agent.objects.all()
    return Agent.objects.filter(
        status=Agent.Status.ACTIVE,
        access_grants__user=user,
        access_grants__capability=AgentAccessGrant.Capability.RUN,
    ).distinct()


class AgentListAPI(PlatformAPI):
    def get(self, request):
        qs = accessible_agents(request.user).select_related("owner").order_by("-created_at")
        return ok(AgentSerializer(qs, many=True).data)

    def post(self, request):
        self.admin_required(request)
        serializer = AgentSerializer(data=request.data)
        if not serializer.is_valid():
            return bad(serializer.errors)
        agent = serializer.save(owner=request.user)
        return ok(AgentSerializer(agent).data, status.HTTP_201_CREATED)


class AgentDetailAPI(PlatformAPI):
    def get(self, request, agent_id):
        obj = get_object_or_404(accessible_agents(request.user), pk=agent_id)
        return ok(AgentSerializer(obj).data)

    def patch(self, request, agent_id):
        self.admin_required(request)
        obj = get_object_or_404(Agent, pk=agent_id)
        serializer = AgentSerializer(obj, data=request.data, partial=True)
        if not serializer.is_valid():
            return bad(serializer.errors)
        serializer.save()
        return ok(AgentSerializer(obj).data)


class VersionsAPI(PlatformAPI):
    def get(self, request, agent_id):
        agent = get_object_or_404(accessible_agents(request.user), pk=agent_id)
        qs = agent.versions.all()
        if not is_platform_admin(request.user):
            qs = qs.filter(status=AgentVersion.Status.PUBLISHED)
        return ok(AgentVersionSerializer(qs, many=True).data)

    def post(self, request, agent_id):
        self.admin_required(request)
        agent = get_object_or_404(Agent, pk=agent_id)
        serializer = AgentVersionSerializer(data=request.data)
        if not serializer.is_valid():
            return bad(serializer.errors)
        data = serializer.validated_data
        try:
            version = create_version(
                agent=agent,
                actor=request.user,
                prompt=data["system_prompt"],
                model_profile=data["model_profile"],
                tools=data.get("tools", []),
            )
        except (DjangoValidationError, IntegrityError) as exc:
            return bad(exc)
        return ok(AgentVersionSerializer(version).data, status.HTTP_201_CREATED)


class VersionDetailAPI(PlatformAPI):
    def get(self, request, agent_id, version_id):
        agent = get_object_or_404(accessible_agents(request.user), pk=agent_id)
        qs = agent.versions.all()
        if not is_platform_admin(request.user):
            qs = qs.filter(status=AgentVersion.Status.PUBLISHED)
        version = get_object_or_404(qs, pk=version_id)
        return ok(AgentVersionSerializer(version).data)

    def patch(self, request, agent_id, version_id):
        self.admin_required(request)
        version = get_object_or_404(AgentVersion, pk=version_id, agent_id=agent_id)
        if version.status == AgentVersion.Status.PUBLISHED:
            return bad("已发布版本不可编辑，请创建新版本", status.HTTP_409_CONFLICT)
        serializer = AgentVersionSerializer(version, data=request.data, partial=True)
        if not serializer.is_valid():
            return bad(serializer.errors)
        data = serializer.validated_data
        with transaction.atomic():
            version = AgentVersion.objects.select_for_update().get(pk=version.pk)
            if version.status == AgentVersion.Status.PUBLISHED:
                return bad("已发布版本不可编辑", status.HTTP_409_CONFLICT)
            if "system_prompt" in data:
                version.system_prompt = data["system_prompt"]
            if "model_profile" in data:
                version.model_profile = data["model_profile"]
            version.save()
            if "tools" in data:
                # Draft grants may be changed, but published grants never expand.
                version.tool_grants.all().delete()
                for tool in data["tools"]:
                    ToolGrant.objects.create(version=version, tool=tool)
        return ok(AgentVersionSerializer(version).data)


class PublishVersionAPI(PlatformAPI):
    def post(self, request, agent_id, version_id):
        self.admin_required(request)
        agent = get_object_or_404(Agent, pk=agent_id)
        try:
            version = publish_version(agent, version_id)
        except AgentVersion.DoesNotExist:
            return bad("未找到该版本", status.HTTP_404_NOT_FOUND)
        except DjangoValidationError as exc:
            return bad(exc, status.HTTP_409_CONFLICT)
        return ok(AgentVersionSerializer(version).data)


class VersionRevokeToolAPI(PlatformAPI):
    def post(self, request, agent_id, version_id, tool_id):
        self.admin_required(request)
        version = get_object_or_404(AgentVersion, pk=version_id, agent_id=agent_id)
        if not revoke_tool(version, tool_id):
            return bad("工具授权不存在或已撤销", status.HTTP_404_NOT_FOUND)
        return ok({"revoked": True})


class CatalogAPI(PlatformAPI):
    def get(self, request, catalog):
        if catalog == "models":
            qs = ModelProfile.objects.select_related("provider").filter(
                enabled=True, provider__enabled=True
            )
            return ok(ModelProfileSerializer(qs, many=True).data)
        if catalog == "tools":
            qs = ToolDefinition.objects.filter(enabled=True)
            if not is_platform_admin(request.user):
                qs = qs.filter(
                    agent_grants__enabled=True,
                    agent_grants__version__status=AgentVersion.Status.PUBLISHED,
                    agent_grants__version__agent__status=Agent.Status.ACTIVE,
                    agent_grants__version__agent__access_grants__user=request.user,
                    agent_grants__version__agent__access_grants__capability=AgentAccessGrant.Capability.RUN,
                ).distinct()
            return ok(ToolCatalogSerializer(qs, many=True).data)
        return bad("无效目录", status.HTTP_404_NOT_FOUND)


class AccessGrantsAPI(PlatformAPI):
    def get(self, request, agent_id):
        self.admin_required(request)
        agent = get_object_or_404(Agent, pk=agent_id)
        return ok(AgentAccessSerializer(agent.access_grants.all(), many=True).data)

    def post(self, request, agent_id):
        self.admin_required(request)
        agent = get_object_or_404(Agent, pk=agent_id)
        serializer = AgentAccessSerializer(data={**request.data, "agent": str(agent.pk)})
        if not serializer.is_valid():
            return bad(serializer.errors)
        try:
            grant = serializer.save()
        except IntegrityError:
            return bad("该用户已经存在此项授权", status.HTTP_409_CONFLICT)
        return ok(AgentAccessSerializer(grant).data, status.HTTP_201_CREATED)


class RevokeAccessAPI(PlatformAPI):
    def delete(self, request, agent_id, grant_id):
        self.admin_required(request)
        deleted, _ = AgentAccessGrant.objects.filter(
            agent_id=agent_id, pk=grant_id
        ).delete()
        if not deleted:
            return bad("授权不存在", status.HTTP_404_NOT_FOUND)
        return ok({"revoked": True})


class CatalogProvisionAPI(PlatformAPI):
    """Superadmin only: register metadata. No arbitrary Python callable or credentials."""

    def post(self, request, catalog):
        self.admin_required(request)
        data = request.data
        if catalog == "providers":
            if any(key in data for key in ("secret_ref", "api_key", "token", "base_url")):
                return bad("凭据和任意 URL 不能通过此 API 提交")
            code = data.get("code")
            name = data.get("name")
            if not isinstance(code, str) or not isinstance(name, str) or not code or not name:
                return bad("code、name 必填")
            from django.core.validators import validate_slug
            try:
                validate_slug(code)
                if len(code) > 64 or len(name) > 120:
                    raise DjangoValidationError("长度超限")
            except DjangoValidationError:
                return bad("provider code 不合法")
            try:
                obj = ModelProvider.objects.create(code=code, name=name, enabled=False)
            except IntegrityError:
                return bad("provider code 已存在", status.HTTP_409_CONFLICT)
            return ok({"id": obj.pk, "code": obj.code, "enabled": obj.enabled}, status.HTTP_201_CREATED)
        if catalog == "tools":
            if any(key in data for key in ("callable", "code_path", "python", "url", "credentials")):
                return bad("不允许提交动态工具执行代码或 URL")
            code, name = data.get("code"), data.get("name")
            if not isinstance(code, str) or not isinstance(name, str) or not code or not name:
                return bad("code、name 必填")
            if len(code) > 100 or len(name) > 120:
                return bad("字段长度超限")
            from django.core.validators import validate_slug
            try:
                validate_slug(code)
            except DjangoValidationError:
                return bad("tool code 不合法")
            # Only a built-in mock tool may be registered in P1-A.
            if code != "mock_sales_summary" or data.get("kind", "mock_read") != "mock_read":
                return bad("P1-A 仅支持 mock_sales_summary 模拟只读工具")
            obj, _ = ToolDefinition.objects.get_or_create(
                code=code,
                defaults={"name": name, "kind": ToolDefinition.Kind.MOCK_READ, "enabled": True},
            )
            return ok(ToolCatalogSerializer(obj).data, status.HTTP_201_CREATED)
        return bad("无效目录", status.HTTP_404_NOT_FOUND)
