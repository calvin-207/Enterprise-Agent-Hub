from django.urls import path
from model_gateway.views import ProviderConfigAPI, ModelProfileConfigAPI, ProviderSyncAPI, ProviderTestAPI, ProviderTemplatesAPI

from agent_catalog.views import (
    AgentListAPI, AgentDetailAPI, VersionsAPI, VersionDetailAPI,
    PublishVersionAPI, VersionRevokeToolAPI, CatalogAPI,
    AccessGrantsAPI, RevokeAccessAPI, CatalogProvisionAPI,
)

urlpatterns = [
    path("model-providers/templates/", ProviderTemplatesAPI.as_view(), name="model-provider-templates"),
    path("model-providers/", ProviderConfigAPI.as_view(), name="model-provider-config"),
    path("model-providers/<int:provider_id>/sync/", ProviderSyncAPI.as_view(), name="model-provider-sync"),
    path("model-providers/<int:provider_id>/test/", ProviderTestAPI.as_view(), name="model-provider-test"),
    path("model-providers/<int:provider_id>/", ProviderConfigAPI.as_view(), name="model-provider-detail"),
    path("model-profiles/", ModelProfileConfigAPI.as_view(), name="model-profile-config"),
    path("model-profiles/<int:profile_id>/", ModelProfileConfigAPI.as_view(), name="model-profile-detail"),
    path("agents/", AgentListAPI.as_view(), name="platform-agents"),
    path("agents/<uuid:agent_id>/", AgentDetailAPI.as_view(), name="platform-agent-detail"),
    path("agents/<uuid:agent_id>/versions/", VersionsAPI.as_view(), name="platform-agent-versions"),
    path("agents/<uuid:agent_id>/versions/<uuid:version_id>/", VersionDetailAPI.as_view(), name="platform-agent-version-detail"),
    path("agents/<uuid:agent_id>/versions/<uuid:version_id>/publish/", PublishVersionAPI.as_view(), name="platform-agent-publish"),
    path("agents/<uuid:agent_id>/versions/<uuid:version_id>/tools/<int:tool_id>/revoke/", VersionRevokeToolAPI.as_view(), name="platform-agent-tool-revoke"),
    path("agents/<uuid:agent_id>/access-grants/", AccessGrantsAPI.as_view(), name="platform-agent-access"),
    path("agents/<uuid:agent_id>/access-grants/<int:grant_id>/", RevokeAccessAPI.as_view(), name="platform-agent-access-revoke"),
    path("catalog/<str:catalog>/", CatalogAPI.as_view(), name="platform-agent-catalog"),
    path("provision/<str:catalog>/", CatalogProvisionAPI.as_view(), name="platform-agent-provision"),
]
