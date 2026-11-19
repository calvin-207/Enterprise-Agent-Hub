"""Platform P1-A contract tests: isolation, publication and safe revocation."""
import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from rest_framework.test import APIClient

from agent_catalog.models import Agent, AgentVersion, ToolGrant
from agent_catalog.services import allowed_tool_ids, is_granted
from model_gateway.models import ModelProfile
from tool_gateway.models import ToolDefinition


@pytest.fixture
def admin(django_user_model):
    return django_user_model.objects.create_superuser(
        username="platform-admin", password="AdminPass!2026", name="Platform Admin"
    )


@pytest.fixture
def member(django_user_model):
    return django_user_model.objects.create_user(
        username="platform-member", password="UserPass!2026", name="Member"
    )


@pytest.fixture
def client_admin(admin):
    client = APIClient()
    client.force_authenticate(user=admin)
    return client


@pytest.fixture
def catalog(db):
    call_command("bootstrap_mock_catalog")
    return ModelProfile.objects.get(model_code="mock-small"), ToolDefinition.objects.get(code="mock_sales_summary")


@pytest.fixture
def configured_agent(client_admin, catalog):
    profile, tool = catalog
    created = client_admin.post("/api/platform/v1/agents/", {
        "code": "sales-analysis", "name": "销售分析", "description": "模拟只读分析",
    }, format="json")
    assert created.status_code == 201, created.data
    agent_id = created.data["data"]["id"]
    version = client_admin.post(f"/api/platform/v1/agents/{agent_id}/versions/", {
        "system_prompt": "分析可信销售数据", "model_profile": profile.pk,
        "tool_ids": [tool.pk],
    }, format="json")
    assert version.status_code == 201, version.data
    return Agent.objects.get(pk=agent_id), AgentVersion.objects.get(pk=version.data["data"]["id"]), tool


@pytest.mark.django_db
def test_platform_requires_auth_and_admin_write(admin, member):
    client = APIClient()
    assert client.get("/api/platform/v1/agents/").status_code == 401
    assert client.post("/api/platform/v1/agents/", {"code": "abc", "name": "ABC"}, format="json").status_code == 401
    client.force_authenticate(user=member)
    assert client.get("/api/platform/v1/agents/").status_code == 200
    assert client.post("/api/platform/v1/agents/", {"code": "abc", "name": "ABC"}, format="json").status_code == 403
    assert client.post("/api/platform/v1/provision/tools/", {"code": "evil"}, format="json").status_code == 403


@pytest.mark.django_db
def test_create_publish_and_immutability(client_admin, configured_agent, member):
    agent, version, tool = configured_agent
    assert version.status == "draft"
    response = client_admin.post(f"/api/platform/v1/agents/{agent.pk}/versions/{version.pk}/publish/")
    assert response.status_code == 200, response.data
    version.refresh_from_db()
    assert version.status == "published"
    agent.refresh_from_db()
    assert agent.status == "active"

    assert client_admin.patch(
        f"/api/platform/v1/agents/{agent.pk}/versions/{version.pk}/",
        {"system_prompt": "tamper"}, format="json",
    ).status_code == 409
    version.system_prompt = "bypass ORM"
    with pytest.raises(ValidationError):
        version.save()
    with pytest.raises(ValidationError):
        ToolGrant.objects.create(version=version, tool=ToolDefinition.objects.create(
            code="another-read-tool", name="Another", enabled=True,
        ))
    assert ToolGrant.objects.filter(version=version, enabled=True).count() == 1

    assert not is_granted(member, agent)
    assert allowed_tool_ids(version, member) == []


@pytest.mark.django_db
def test_user_grant_and_revocation_are_rechecked(client_admin, configured_agent, member):
    agent, version, tool = configured_agent
    assert client_admin.post(f"/api/platform/v1/agents/{agent.pk}/versions/{version.pk}/publish/").status_code == 200
    version.refresh_from_db()
    client = APIClient()
    client.force_authenticate(user=member)
    assert client.get(f"/api/platform/v1/agents/{agent.pk}/").status_code == 404
    grant = client_admin.post(f"/api/platform/v1/agents/{agent.pk}/access-grants/", {
        "user": member.pk, "capability": "run"
    }, format="json")
    assert grant.status_code == 201, grant.data
    assert client_admin.post(f"/api/platform/v1/agents/{agent.pk}/access-grants/", {
        "user": member.pk, "capability": "manage"
    }, format="json").status_code == 400
    # 校验失败时 msg 必须是可读文本，不允许泄漏 ErrorDetail repr（如 {'user': [ErrorDetail(string=...)]}）
    missing_user = client_admin.post(f"/api/platform/v1/agents/{agent.pk}/access-grants/", {
        "user": 999999, "capability": "run"
    }, format="json")
    assert missing_user.status_code == 400
    assert "ErrorDetail" not in missing_user.data["msg"]
    assert missing_user.data["msg"].startswith("user:")
    assert client.get(f"/api/platform/v1/agents/{agent.pk}/").status_code == 200
    assert str(version.pk) in [str(x["id"]) for x in client.get(
        f"/api/platform/v1/agents/{agent.pk}/versions/"
    ).data["data"]]
    assert tool.pk in allowed_tool_ids(version, member)
    assert client.get("/api/platform/v1/catalog/tools/").data["data"][0]["code"] == "mock_sales_summary"

    revoke = client_admin.post(
        f"/api/platform/v1/agents/{agent.pk}/versions/{version.pk}/tools/{tool.pk}/revoke/"
    )
    assert revoke.status_code == 200
    assert allowed_tool_ids(version, member) == []
    assert client_admin.post(f"/api/platform/v1/agents/{agent.pk}/versions/{version.pk}/publish/").status_code == 409

    delete = client_admin.delete(
        f"/api/platform/v1/agents/{agent.pk}/access-grants/{grant.data['data']['id']}/"
    )
    assert delete.status_code == 200
    assert not is_granted(member, agent)
    assert client.get(f"/api/platform/v1/agents/{agent.pk}/").status_code == 404


@pytest.mark.django_db
def test_cannot_publish_without_tools_or_enabled_model(client_admin, catalog):
    profile, tool = catalog
    agent_response = client_admin.post("/api/platform/v1/agents/", {
        "code": "new-agent", "name": "Test"
    }, format="json")
    agent_id = agent_response.data["data"]["id"]
    response = client_admin.post(f"/api/platform/v1/agents/{agent_id}/versions/", {
        "system_prompt": "Safe", "model_profile": profile.pk
    }, format="json")
    version_id = response.data["data"]["id"]
    assert client_admin.post(f"/api/platform/v1/agents/{agent_id}/versions/{version_id}/publish/").status_code == 409
    assert client_admin.patch(
        f"/api/platform/v1/agents/{agent_id}/versions/{version_id}/",
        {"tool_ids": [tool.pk]}, format="json",
    ).status_code == 200
    profile.enabled = False
    profile.save(update_fields=["enabled"])
    assert client_admin.post(f"/api/platform/v1/agents/{agent_id}/versions/{version_id}/publish/").status_code == 409


@pytest.mark.django_db
def test_secret_and_arbitrary_code_are_rejected(client_admin, catalog):
    result = client_admin.post("/api/platform/v1/provision/providers/", {
        "code": "unsafe", "name": "Bad", "api_key": "do-not-store"
    }, format="json")
    assert result.status_code == 400
    assert client_admin.post("/api/platform/v1/provision/tools/", {
        "code": "run_shell", "name": "shell", "callable": "os.system"
    }, format="json").status_code == 400
    assert client_admin.post("/api/platform/v1/provision/tools/", {
        "code": "untrusted", "name": "unsafe"
    }, format="json").status_code == 400
