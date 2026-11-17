import { ajaxGet, ajaxPost } from "@/api/request";

const base = "/api/automation/executions/";

export const listExecutions = (params) => ajaxGet({ url: base, params });
export const getExecution = (id) => ajaxGet({ url: `${base}${id}/` });
export const createExecution = (task_type) => ajaxPost({ url: base, params: { task_type } });
export const retryExecution = (id) => ajaxPost({ url: `${base}${id}/retry/`, params: {} });
