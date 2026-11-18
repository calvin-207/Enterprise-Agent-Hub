<template>
  <div class="agent-page">
    <header class="page-head">
      <div>
        <p class="eyebrow">ENTERPRISE AGENT HUB / CONFIGURATION</p>
        <h1>Agent 管理</h1>
        <p class="subtitle">配置 Agent、发布不可变版本及管理运行授权。本阶段仅管理配置，不执行 Agent。</p>
      </div>
      <div class="actions">
        <el-button :icon="Refresh" :loading="loading" @click="reload">刷新</el-button>
        <el-button type="primary" :icon="Plus" @click="openAgent()">创建 Agent</el-button>
      </div>
    </header>
    <el-alert
      class="notice" type="info" show-icon :closable="false"
      title="当前为 P1-A 配置阶段"
      description="仅支持已授权的模型配置与模拟只读工具。Agent Runtime 和真实模型调用将在 P1-B/P1-C 完成后启用。"
    />

    <el-card shadow="never" class="card">
      <el-table :data="agents" v-loading="loading" row-key="id" stripe>
        <el-table-column prop="name" label="Agent 名称" min-width="160"/>
        <el-table-column prop="code" label="唯一标识" min-width="160"/>
        <el-table-column prop="description" label="说明" min-width="200" show-overflow-tooltip/>
        <el-table-column label="状态" width="115">
          <template #default="{ row }"><el-tag :type="row.status === 'active' ? 'success' : 'info'">{{ statusLabel(row.status) }}</el-tag></template>
        </el-table-column>
        <el-table-column label="操作" min-width="240" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openVersions(row)">版本</el-button>
            <el-button link @click="openAgent(row)">编辑</el-button>
            <el-button link type="success" @click="openGrants(row)">用户授权</el-button>
          </template>
        </el-table-column>
        <template #empty><el-empty description="还没有 Agent，请先创建定义" /></template>
      </el-table>
    </el-card>

    <el-dialog v-model="showAgent" :title="editingAgent ? '编辑 Agent' : '创建 Agent'" width="min(520px, 96vw)" destroy-on-close>
      <el-form :model="agentForm" label-position="top" ref="agentRef" :rules="agentRules">
        <el-form-item label="Agent 标识（创建后不建议变更）" prop="code">
          <el-input v-model.trim="agentForm.code" maxlength="100" placeholder="例如 sales-analysis" :disabled="!!editingAgent"/>
        </el-form-item>
        <el-form-item label="名称" prop="name"><el-input v-model.trim="agentForm.name" maxlength="120"/></el-form-item>
        <el-form-item label="说明">
          <el-input v-model="agentForm.description" type="textarea" maxlength="500" :rows="3"/>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAgent = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveAgent">保存</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="showVersions" :title="(selected?.name || '') + ' · 版本管理'" size="min(860px, 96vw)">
      <div class="drawer-intro">
        <span>已发布版本不可修改；需要更改提示词或模型时，请创建新版本。</span>
        <el-button type="primary" size="small" :icon="Plus" @click="openVersion()">新建版本</el-button>
      </div>
      <el-table :data="versions" v-loading="detailsLoading" stripe>
        <el-table-column prop="version_number" label="版本" width="80"/>
        <el-table-column label="模型" min-width="105">
          <template #default="{ row }">{{ modelLabel(row.model_profile) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="105">
          <template #default="{ row }">
            <el-tag :type="row.status === 'published' ? 'success' : 'warning'">{{ row.status === 'published' ? '已发布' : '草稿' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="工具" min-width="150">
          <template #default="{ row }">
            <el-tag v-for="t in row.tools" :key="t.id" class="tag" :type="t.enabled ? 'info' : 'danger'">
              {{ t.code }}{{ t.enabled ? '' : '（已撤销）' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openVersion(row)">{{ row.status === 'draft' ? '编辑' : '详情' }}</el-button>
            <el-button v-if="row.status === 'draft'" link type="success" :loading="saving" @click="publish(row)">发布</el-button>
            <el-button v-if="row.status === 'published'" link type="warning" @click="openRevocation(row)">撤权</el-button>
          </template>
        </el-table-column>
        <template #empty><el-empty description="尚无版本，请新建草稿" /></template>
      </el-table>
      <el-alert class="notice" type="warning" :closable="false" title="请先运行 bootstrap_mock_catalog 命令准备模拟模型和只读工具；未配置时无法发布。"/>
    </el-drawer>

    <el-dialog v-model="showVersionForm" :title="editingVersion ? '版本配置' : '新建 Agent 版本'" width="min(680px, 96vw)" destroy-on-close>
      <el-form :model="versionForm" label-position="top" ref="versionRef" :rules="versionRules">
        <el-form-item label="系统提示词" prop="system_prompt">
          <el-input v-model="versionForm.system_prompt" type="textarea" :rows="6" maxlength="20000" show-word-limit :disabled="versionReadOnly"/>
        </el-form-item>
        <el-form-item label="模型配置" prop="model_profile">
          <el-select v-model="versionForm.model_profile" placeholder="选择已启用的模型" style="width:100%" :disabled="versionReadOnly">
            <el-option v-for="m in models" :key="m.id" :value="m.id" :label="m.provider_code + ' / ' + m.model_code + (m.is_default ? '（默认）' : '')"/>
          </el-select>
        </el-form-item>
        <el-form-item label="允许使用的只读工具" prop="tool_ids">
          <el-select v-model="versionForm.tool_ids" multiple style="width:100%" placeholder="选择一个或多个工具" :disabled="versionReadOnly">
            <el-option v-for="t in tools" :key="t.id" :label="t.name + ' (' + t.code + ')'" :value="t.id"/>
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showVersionForm = false">关闭</el-button>
        <el-button v-if="!versionReadOnly" type="primary" :loading="saving" @click="saveVersion">保存草稿</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showRevoke" title="撤销已发布工具授权" width="min(540px, 96vw)">
      <el-alert title="撤销后将立即停止该工具后续授权，已发布版本不可重新启用此项授权。" type="warning" :closable="false"/>
      <div v-for="tool in revokeVersion?.tools?.filter(t => t.enabled)" :key="tool.id" class="revoke-row">
        <span>{{ tool.code }}</span>
        <el-button type="danger" size="small" plain :loading="saving" @click="revokeTool(tool)">撤销</el-button>
      </div>
      <p v-if="!revokeVersion?.tools?.some(t => t.enabled)">没有可撤销的工具。</p>
    </el-dialog>

    <el-drawer v-model="showGrants" :title="(selected?.name || '') + ' · 用户运行授权'" size="min(640px, 96vw)">
      <el-alert class="notice" type="info" :closable="false" title="授权用户 ID 可在现有用户管理模块中查询。授权只允许运行 Agent，不赋予配置管理或业务 Tool 的额外权限。"/>
      <el-form inline @submit.prevent="addGrant">
        <el-form-item label="用户 ID">
          <el-input v-model.trim="grantUserId" placeholder="请输入平台用户 ID" style="width:240px"/>
        </el-form-item>
        <el-form-item><el-button type="primary" :loading="saving" @click="addGrant">授予运行权限</el-button></el-form-item>
      </el-form>
      <el-table :data="grants" v-loading="detailsLoading" stripe>
        <el-table-column prop="id" label="授权编号" width="115"/>
        <el-table-column prop="user" label="用户 ID" min-width="170"/>
        <el-table-column prop="capability" label="权限" width="90"/>
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button type="danger" link :loading="saving" @click="removeGrant(row)">撤销</el-button>
          </template>
        </el-table-column>
        <template #empty><el-empty description="尚未授权用户" /></template>
      </el-table>
    </el-drawer>
  </div>
</template>

<script setup name="agentManage">
import { onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Refresh } from "@element-plus/icons-vue";
import {
  listAgents, createAgent, updateAgent, listAgentVersions, createAgentVersion,
  updateAgentVersion, publishAgentVersion, revokeAgentTool,
  listModelCatalog, listToolCatalog, listAgentGrants,
  createAgentGrant, revokeAgentGrant,
} from "./api";

const agents = ref([]);
const versions = ref([]);
const models = ref([]);
const tools = ref([]);
const grants = ref([]);
const selected = ref(null);
const loading = ref(false);
const detailsLoading = ref(false);
const saving = ref(false);
const showAgent = ref(false);
const showVersions = ref(false);
const showVersionForm = ref(false);
const showRevoke = ref(false);
const showGrants = ref(false);
const editingAgent = ref(null);
const editingVersion = ref(null);
const revokeVersion = ref(null);
const versionReadOnly = ref(false);
const agentForm = ref({});
const versionForm = ref({});
const agentRef = ref(null);
const versionRef = ref(null);
const grantUserId = ref("");
const agentRules = {
  code: [
    { required: true, message: "请输入 Agent 标识", trigger: "blur" },
    { pattern: /^[a-zA-Z0-9_-]+$/, message: "仅允许字母、数字、下划线和连字符", trigger: "blur" },
  ],
  name: [{ required: true, message: "请输入名称", trigger: "blur" }],
};
const versionRules = {
  system_prompt: [{ required: true, message: "请输入系统提示词", trigger: "blur" }],
  model_profile: [{ required: true, message: "请选择模型", trigger: "change" }],
  tool_ids: [{ type: "array", min: 1, message: "至少选择一个已启用只读工具", trigger: "change" }],
};
const statusLabel = (s) => ({ draft: "草稿", active: "已发布", disabled: "已停用" }[s] || s);
const modelLabel = (id) => models.value.find((m) => m.id === id)?.model_code || `模型 #${id}`;
function messageError(error, fallback) { ElMessage.error(error?.message || fallback); }
async function reload() {
  loading.value = true;
  try {
    const [a, m, t] = await Promise.all([listAgents(), listModelCatalog(), listToolCatalog()]);
    if ([a, m, t].some(x => x.code !== 2000)) throw new Error(a.msg || m.msg || t.msg || "读取配置失败");
    agents.value = a.data || [];
    models.value = m.data || [];
    tools.value = t.data || [];
  } catch (e) { messageError(e, "Agent 列表读取失败"); }
  finally { loading.value = false; }
}
function openAgent(row = null) {
  editingAgent.value = row;
  agentForm.value = row ? { code: row.code, name: row.name, description: row.description } :
    { code: "", name: "", description: "" };
  showAgent.value = true;
}
async function saveAgent() {
  try { await agentRef.value.validate(); } catch { return; }
  saving.value = true;
  try {
    const data = editingAgent.value ? { name: agentForm.value.name, description: agentForm.value.description } : agentForm.value;
    const res = editingAgent.value ? await updateAgent(editingAgent.value.id, data) : await createAgent(data);
    if (res.code !== 2000) throw new Error(res.msg || "保存失败");
    showAgent.value = false;
    ElMessage.success("Agent 已保存");
    await reload();
  } catch (e) { messageError(e, "保存 Agent 失败"); }
  finally { saving.value = false; }
}
async function refreshVersions() {
  if (!selected.value) return;
  detailsLoading.value = true;
  try {
    const res = await listAgentVersions(selected.value.id);
    if (res.code !== 2000) throw new Error(res.msg || "获取版本失败");
    versions.value = res.data || [];
    await reload();
  } catch (e) { messageError(e, "读取版本失败"); }
  finally { detailsLoading.value = false; }
}
async function openVersions(row) {
  selected.value = row;
  showVersions.value = true;
  await refreshVersions();
}
function openVersion(row = null) {
  editingVersion.value = row;
  versionReadOnly.value = row?.status === "published";
  versionForm.value = row ? {
    system_prompt: row.system_prompt, model_profile: row.model_profile,
    tool_ids: row.tools.filter((t) => t.enabled).map((t) => t.id),
  } : { system_prompt: "", model_profile: models.value.find(m => m.is_default)?.id ?? null, tool_ids: [] };
  showVersionForm.value = true;
}
async function saveVersion() {
  try { await versionRef.value.validate(); } catch { return; }
  saving.value = true;
  try {
    const a = selected.value.id;
    const res = editingVersion.value
      ? await updateAgentVersion(a, editingVersion.value.id, versionForm.value)
      : await createAgentVersion(a, versionForm.value);
    if (res.code !== 2000) throw new Error(res.msg || "保存失败");
    showVersionForm.value = false;
    ElMessage.success("版本草稿已保存");
    await refreshVersions();
  } catch (e) { messageError(e, "保存版本失败"); }
  finally { saving.value = false; }
}
async function publish(row) {
  try {
    await ElMessageBox.confirm(`发布 v${row.version_number} 后，其模型、提示词和可用工具不可扩充。确定发布？`, "发布版本", { type: "warning" });
  } catch { return; }
  saving.value = true;
  try {
    const res = await publishAgentVersion(selected.value.id, row.id);
    if (res.code !== 2000) throw new Error(res.msg || "发布失败");
    ElMessage.success("版本已发布");
    await refreshVersions();
  } catch (e) { messageError(e, "发布失败"); }
  finally { saving.value = false; }
}
function openRevocation(row) {
  revokeVersion.value = row;
  showRevoke.value = true;
}
async function revokeTool(tool) {
  try {
    await ElMessageBox.confirm(`确定撤销 ${tool.code}？已发布版本不能重新授权该工具。`, "确认撤销", { type: "warning" });
  } catch { return; }
  saving.value = true;
  try {
    const res = await revokeAgentTool(selected.value.id, revokeVersion.value.id, tool.id);
    if (res.code !== 2000) throw new Error(res.msg || "撤销失败");
    ElMessage.success("工具授权已撤销");
    await refreshVersions();
    revokeVersion.value = versions.value.find((v) => v.id === revokeVersion.value.id) || null;
  } catch (e) { messageError(e, "撤销工具失败"); }
  finally { saving.value = false; }
}
async function refreshGrants() {
  detailsLoading.value = true;
  try {
    const res = await listAgentGrants(selected.value.id);
    if (res.code !== 2000) throw new Error(res.msg);
    grants.value = res.data || [];
  } catch (e) { messageError(e, "读取授权失败"); }
  finally { detailsLoading.value = false; }
}
async function openGrants(row) {
  selected.value = row;
  grantUserId.value = "";
  showGrants.value = true;
  await refreshGrants();
}
async function addGrant() {
  if (!grantUserId.value) return ElMessage.warning("请输入用户 ID");
  saving.value = true;
  try {
    const res = await createAgentGrant(selected.value.id, { user: grantUserId.value, capability: "run" });
    if (res.code !== 2000) throw new Error(res.msg || "授权失败");
    grantUserId.value = "";
    ElMessage.success("运行授权已创建");
    await refreshGrants();
  } catch (e) { messageError(e, "用户授权失败"); }
  finally { saving.value = false; }
}
async function removeGrant(row) {
  try { await ElMessageBox.confirm(`确定撤销用户 ${row.user} 的运行权限？`, "确认撤销", { type: "warning" }); }
  catch { return; }
  saving.value = true;
  try {
    const res = await revokeAgentGrant(selected.value.id, row.id);
    if (res.code !== 2000) throw new Error(res.msg);
    ElMessage.success("已撤销权限");
    await refreshGrants();
  } catch (e) { messageError(e, "撤销失败"); }
  finally { saving.value = false; }
}
onMounted(reload);
</script>

<style scoped>
.agent-page { max-width: 1520px; margin: 0 auto; padding: 24px; }
.page-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; margin-bottom: 22px; }
.eyebrow { font-size: 12px; letter-spacing: .12em; color: var(--el-color-primary); font-weight: 700; margin: 0 0 8px; }
h1 { font-size: 28px; margin: 0 0 8px; }
.subtitle { color: var(--el-text-color-secondary); line-height: 1.7; margin: 0; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; flex-shrink: 0; }
.notice { margin-bottom: 20px; }
.card { border-radius: 12px; }
.drawer-intro { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 18px; color: var(--el-text-color-secondary); font-size: 13px; }
.tag { margin: 2px 4px 2px 0; }
.revoke-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid var(--el-border-color-light); }
@media (max-width: 740px) {
  .agent-page { padding: 12px; }
  .page-head, .drawer-intro { flex-direction: column; }
  h1 { font-size: 23px; }
}
</style>
