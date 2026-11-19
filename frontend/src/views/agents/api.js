import { ajaxGet, ajaxPost, ajaxPatch, ajaxDelete } from "@/api/request";

const base = "/api/platform/v1/";

export const listAgents = () => ajaxGet({ url: `${base}agents/` });
export const createAgent = (data) => ajaxPost({ url: `${base}agents/`, params: data });
export const updateAgent = (id, data) => ajaxPatch({ url: `${base}agents/${id}/`, params: data });
export const listAgentVersions = (id) => ajaxGet({ url: `${base}agents/${id}/versions/` });
export const createAgentVersion = (id, data) => ajaxPost({ url: `${base}agents/${id}/versions/`, params: data });
export const updateAgentVersion = (agentId, versionId, data) =>
  ajaxPatch({ url: `${base}agents/${agentId}/versions/${versionId}/`, params: data });
export const publishAgentVersion = (agentId, versionId) =>
  ajaxPost({ url: `${base}agents/${agentId}/versions/${versionId}/publish/`, params: {} });
export const revokeAgentTool = (agentId, versionId, toolId) =>
  ajaxPost({ url: `${base}agents/${agentId}/versions/${versionId}/tools/${toolId}/revoke/`, params: {} });
export const listModelCatalog = () => ajaxGet({ url: `${base}catalog/models/` });
export const listToolCatalog = () => ajaxGet({ url: `${base}catalog/tools/` });
export const listAgentGrants = (id) => ajaxGet({ url: `${base}agents/${id}/access-grants/` });
export const createAgentGrant = (id, data) =>
  ajaxPost({ url: `${base}agents/${id}/access-grants/`, params: data });
export const revokeAgentGrant = (id, grantId) =>
  ajaxDelete({ url: `${base}agents/${id}/access-grants/${grantId}/` });

export const listRuns = () => ajaxGet({ url: `${base}runs/` });
export const createRun = (data, idempotencyKey) =>
  ajaxPost({ url: `${base}runs/`, params: data, headers: { "Idempotency-Key": idempotencyKey } });
export const getRun = (id) => ajaxGet({ url: `${base}runs/${id}/` });
export const getRunSteps = (id) => ajaxGet({ url: `${base}runs/${id}/steps/` });
export const getRunEvents = (id) => ajaxGet({ url: `${base}runs/${id}/events/` });

export const cancelRun = (id) => ajaxPost({ url: `${base}runs/${id}/cancel/`, params: {} });
export const getRunUsage = (id) => ajaxGet({ url: `${base}runs/${id}/usage/` });

export const listProviders = () => ajaxGet({ url: `${base}model-providers/` });
export const listProviderTemplates = () => ajaxGet({ url: `${base}model-providers/templates/` });
export const createProvider = (params) => ajaxPost({ url: `${base}model-providers/`, params });
export const updateProvider = (id, params) => ajaxPatch({ url: `${base}model-providers/${id}/`, params });
export const listProfiles = () => ajaxGet({ url: `${base}model-profiles/` });
export const createProfile = (params) => ajaxPost({ url: `${base}model-profiles/`, params });
export const updateProfile = (id, params) => ajaxPatch({ url: `${base}model-profiles/${id}/`, params });

export const listSessions = () => ajaxGet({ url: `${base}sessions/` });
export const createSession = (params) => ajaxPost({ url: `${base}sessions/`, params });
export const getSession = (id) => ajaxGet({ url: `${base}sessions/${id}/` });
export const updateSession = (id, params) => ajaxPatch({ url: `${base}sessions/${id}/`, params });
export const getSessionMessages = (id, after = 0) => ajaxGet({
  url: `${base}sessions/${id}/messages/`, params: { after, limit: 100 },
});
export const submitSessionRun = (id, message, key) => ajaxPost({
  url: `${base}sessions/${id}/runs/`,
  params: { message, deadline_seconds: 120 }, headers: { "Idempotency-Key": key },
});

export const syncProviderModels = (id) => ajaxPost({ url: `${base}model-providers/${id}/sync/`, params: {} });
export const testProviderConnection = (id) => ajaxPost({ url: `${base}model-providers/${id}/test/`, params: {} });
