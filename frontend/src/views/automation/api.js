import { ajaxGet, ajaxPost, ajaxPatch, ajaxDelete } from "@/api/request";

const base = "/api/automation/executions/";

export const listExecutions = (params) => ajaxGet({ url: base, params });
export const getExecution = (id) => ajaxGet({ url: `${base}${id}/` });
export const createExecution = (task_type) => ajaxPost({ url: base, params: { task_type } });
export const retryExecution = (id) => ajaxPost({ url: `${base}${id}/retry/`, params: {} });

const definitions = "/api/automation/definitions/";
const schedules = "/api/automation/schedules/";

export const listDefinitions = () => ajaxGet({ url: definitions });
export const createDefinition = (data) => ajaxPost({ url: definitions, params: data });
export const updateDefinition = (id, data) => ajaxPatch({ url: `${definitions}${id}/`, params: data });
export const deleteDefinition = (id) => ajaxDelete({ url: `${definitions}${id}/` });

export const listSchedules = () => ajaxGet({ url: schedules });
export const createSchedule = (data) => ajaxPost({ url: schedules, params: data });
export const updateSchedule = (id, data) => ajaxPatch({ url: `${schedules}${id}/`, params: data });
export const deleteSchedule = (id) => ajaxDelete({ url: `${schedules}${id}/` });
export const runSchedule = (id) => ajaxPost({ url: `${schedules}${id}/run/`, params: {} });
