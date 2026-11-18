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
