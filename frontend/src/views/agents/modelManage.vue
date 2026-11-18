<template>
  <div class="models-page">
    <header class="header">
      <div><p class="eyebrow">ENTERPRISE AGENT HUB / MODEL GATEWAY</p>
        <h1>AI 模型管理</h1>
        <p class="description">添加供应商、同步模型目录，再手动配置启停、单价及默认模型。API Key 可使用环境变量引用或加密保存。</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="reload">刷新</el-button>
    </header>
    <el-alert type="warning" show-icon :closable="false" class="alert"
      title="同步模型只导入供应商返回的模型 ID，并不代表模型已通过推理验证"
      description="新同步模型默认未启用；同步不会覆盖已有模型的名称、价格、默认标记及启停状态。请手工核对模型能力与费用。" />
    <el-tabs v-model="tab">
      <el-tab-pane name="providers" label="模型提供商">
        <div class="toolbar"><strong>Provider 列表</strong><el-button type="primary" :icon="Plus" @click="openProvider()">新增 Provider</el-button></div>
        <el-table :data="providers" v-loading="loading" stripe>
          <el-table-column prop="code" label="标识" min-width="130"/>
          <el-table-column prop="name" label="名称" min-width="160"/>
          <el-table-column prop="adapter_type" label="适配器" min-width="110"/>
          <el-table-column prop="secret_ref" label="密钥环境变量引用" min-width="220">
            <template #default="{ row }">{{ row.secret_ref || "无需密钥" }}</template>
          </el-table-column>
          <el-table-column label="启用状态" width="95">
            <template #default="{ row }"><el-tag :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '启用' : '停用' }}</el-tag></template>
          </el-table-column>
          <el-table-column label="同步时间" min-width="165"><template #default="{ row }">{{ row.last_sync_at ? new Date(row.last_sync_at).toLocaleString("zh-CN") : "未同步" }}</template></el-table-column>
          <el-table-column label="操作" width="180"><template #default="{ row }">
            <el-button link type="primary" @click="openProvider(row)">编辑</el-button>
            <el-button link type="success" :loading="syncingId === row.id" :disabled="!row.enabled" @click="syncModels(row)">同步模型</el-button>
          </template></el-table-column>
        </el-table>
      </el-tab-pane>
      <el-tab-pane name="profiles" label="模型列表与价格">
        <div class="toolbar"><strong>模型配置</strong><el-button type="primary" :icon="Plus" :disabled="providers.length === 0" @click="openProfile()">新增模型</el-button></div>
        <el-table :data="profiles" v-loading="loading" stripe>
          <el-table-column prop="name" label="名称" min-width="140"/>
          <el-table-column label="Provider" min-width="120"><template #default="{ row }">{{ providerLabel(row.provider) }}</template></el-table-column>
          <el-table-column prop="model_code" label="模型 ID" min-width="140"/>
          <el-table-column label="输入 / 100 万 Token" min-width="150"><template #default="{ row }">{{ row.input_price_per_million }} USD</template></el-table-column>
          <el-table-column label="输出 / 100 万 Token" min-width="150"><template #default="{ row }">{{ row.output_price_per_million }} USD</template></el-table-column>
          <el-table-column prop="max_output_tokens" label="单次输出上限" width="120"/>
          <el-table-column label="默认" width="75"><template #default="{ row }"><el-tag v-if="row.is_default" type="success">默认</el-tag><span v-else>—</span></template></el-table-column>
          <el-table-column label="来源" width="80"><template #default="{ row }">{{ row.source === 'sync' ? '同步' : '手动' }}</template></el-table-column>
          <el-table-column label="状态" width="80"><template #default="{ row }"><el-tag :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '启用' : '停用' }}</el-tag></template></el-table-column>
          <el-table-column label="操作" width="85"><template #default="{ row }"><el-button link type="primary" @click="openProfile(row)">编辑</el-button></template></el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="showProvider" :title="editProvider ? '编辑 Provider' : '新增 Provider'" width="min(540px, 96vw)">
      <el-form ref="providerRef" :model="providerForm" label-position="top">
        <el-form-item label="唯一标识" required><el-input v-model.trim="providerForm.code" maxlength="64" :disabled="!!editProvider" placeholder="例如 openai-primary"/></el-form-item>
        <el-form-item label="名称" required><el-input v-model.trim="providerForm.name" maxlength="120"/></el-form-item>
        <el-form-item label="适配类型">
          <el-select v-model="providerForm.adapter_type" style="width:100%">
            <el-option value="openai" label="OpenAI 官方"/>
            <el-option value="openai_compatible" label="OpenAI 兼容接口（域名白名单）"/>
            <el-option value="mock" label="Mock（离线测试）"/>
          </el-select>
        </el-form-item>
        <el-form-item v-if="providerForm.adapter_type === 'openai_compatible'" label="API Base URL">
          <el-input v-model.trim="providerForm.base_url" placeholder="https://trusted.provider.example/v1"/>
          <small>域名需由运维预先添加至 EAH_MODEL_ALLOWED_HOSTS。</small>
        </el-form-item>
        <el-form-item label="密钥引用（env:...，可选）">
          <el-input v-model.trim="providerForm.secret_ref" :disabled="providerForm.adapter_type === 'mock'"
            placeholder="env:EAH_MODEL_KEY_MAIN 或 env:OPENAI_API_KEY"/>
        </el-form-item>
        <el-form-item v-if="providerForm.adapter_type !== 'mock'" label="API Key（可选，写入时加密）">
          <el-input v-model="providerForm.api_key" type="password" show-password autocomplete="new-password" placeholder="留空保留已有密钥"/>
          <small>{{ editProvider?.has_stored_key ? "已安全存储密钥，留空不会修改" : "服务器需配置 EAH_MODEL_ENCRYPTION_KEY" }}</small>
        </el-form-item>
        <el-form-item v-if="editProvider?.has_stored_key" label="清除已存密钥">
          <el-switch v-model="providerForm.clear_api_key"/>
        </el-form-item>
        <el-form-item label="启用"><el-switch v-model="providerForm.enabled"/></el-form-item>
      </el-form>
      <template #footer><el-button @click="showProvider = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveProvider">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="showProfile" :title="editProfile ? '编辑模型' : '新增模型'" width="min(580px, 96vw)">
      <el-form :model="profileForm" label-position="top">
        <el-form-item label="Provider">
          <el-select v-model="profileForm.provider" style="width:100%">
            <el-option v-for="p in providers" :key="p.id" :value="p.id" :label="p.name + ' (' + p.code + ')'" />
          </el-select>
        </el-form-item>
        <el-form-item label="模型名称"><el-input v-model.trim="profileForm.name" maxlength="120"/></el-form-item>
        <el-form-item label="模型 ID"><el-input v-model.trim="profileForm.model_code" maxlength="120" placeholder="例如 gpt-4o-mini"/></el-form-item>
        <el-row :gutter="12">
          <el-col :span="12"><el-form-item label="输入价格（USD/百万 Token）"><el-input v-model="profileForm.input_price_per_million"/></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="输出价格（USD/百万 Token）"><el-input v-model="profileForm.output_price_per_million"/></el-form-item></el-col>
        </el-row>
        <el-form-item label="最大输出 Token"><el-input-number v-model="profileForm.max_output_tokens" :min="1" :max="16384" style="width:100%"/></el-form-item>
        <el-form-item label="设为平台默认模型"><el-switch v-model="profileForm.is_default" :disabled="!profileForm.enabled"/></el-form-item>
        <el-form-item label="启用"><el-switch v-model="profileForm.enabled"/></el-form-item>
      </el-form>
      <el-alert type="info" :closable="false" title="价格由管理员维护，仅用于费用估算，实际费用以模型供应商账单为准。"/>
      <template #footer><el-button @click="showProfile = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveProfile">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup name="modelManage">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { Plus, Refresh } from "@element-plus/icons-vue";
import { listProviders, createProvider, updateProvider, listProfiles, createProfile, updateProfile, syncProviderModels } from "./api";

const tab = ref("providers");
const providers = ref([]);
const profiles = ref([]);
const loading = ref(false);
const saving = ref(false);
const syncingId = ref(null);
const showProvider = ref(false);
const showProfile = ref(false);
const editProvider = ref(null);
const editProfile = ref(null);
const providerForm = ref({});
const profileForm = ref({});
const providerLabel = id => providers.value.find(p => p.id === id)?.code || String(id);

async function reload() {
  loading.value = true;
  try {
    const [p, m] = await Promise.all([listProviders(), listProfiles()]);
    if (p.code !== 2000 || m.code !== 2000) throw new Error(p.msg || m.msg || "读取失败");
    providers.value = p.data || [];
    profiles.value = m.data || [];
  } catch (e) { ElMessage.error(e?.message || "读取模型配置失败，请检查管理员权限"); }
  finally { loading.value = false; }
}
function openProvider(item = null) {
  editProvider.value = item;
  providerForm.value = item ? {
    code: item.code, name: item.name, adapter_type: item.adapter_type,
    secret_ref: item.secret_ref, enabled: item.enabled, base_url: item.base_url || "", api_key: "", clear_api_key: false,
  } : { code: "", name: "", adapter_type: "openai", secret_ref: "", base_url: "", api_key: "", clear_api_key: false, enabled: false };
  showProvider.value = true;
}
function openProfile(item = null) {
  editProfile.value = item;
  profileForm.value = item ? {
    provider: item.provider, name: item.name, model_code: item.model_code,
    input_price_per_million: item.input_price_per_million,
    output_price_per_million: item.output_price_per_million,
    max_output_tokens: item.max_output_tokens, enabled: item.enabled, is_default: item.is_default,
  } : {
    provider: providers.value[0]?.id ?? null, name: "", model_code: "",
    input_price_per_million: "0.000000", output_price_per_million: "0.000000",
    max_output_tokens: 1024, enabled: false, is_default: false,
  };
  showProfile.value = true;
}
async function saveProvider() {
  if (!providerForm.value.code || !providerForm.value.name) return ElMessage.warning("标识和名称必填");
  saving.value = true;
  try {
    const data = { ...providerForm.value };
    if (data.adapter_type === "mock") { data.secret_ref = ""; data.base_url = ""; }
    if (data.adapter_type === "openai") data.base_url = "";
    if (!data.api_key) delete data.api_key;
    if (!data.clear_api_key) delete data.clear_api_key;
    const result = editProvider.value
      ? await updateProvider(editProvider.value.id, data) : await createProvider(data);
    if (result.code !== 2000) throw new Error(result.msg || "保存失败");
    showProvider.value = false;
    ElMessage.success("Provider 已保存");
    await reload();
  } catch (e) { ElMessage.error(e?.message || "保存失败"); }
  finally { saving.value = false; }
}
async function saveProfile() {
  if (!profileForm.value.provider || !profileForm.value.name || !profileForm.value.model_code) return ElMessage.warning("模型信息不完整");
  saving.value = true;
  try {
    const result = editProfile.value
      ? await updateProfile(editProfile.value.id, profileForm.value)
      : await createProfile(profileForm.value);
    if (result.code !== 2000) throw new Error(result.msg || "保存失败");
    showProfile.value = false;
    ElMessage.success("模型配置已保存");
    await reload();
  } catch (e) { ElMessage.error(e?.message || "保存失败"); }
  finally { saving.value = false; }
}
onMounted(reload);
</script>

<style scoped>
.models-page { max-width: 1540px; margin: 0 auto; padding: 24px; }
.header { display: flex; justify-content: space-between; gap: 12px; align-items: start; margin-bottom: 18px; }
.eyebrow { color: var(--el-color-primary); letter-spacing: .1em; font-size: 12px; font-weight: 700; margin: 0 0 6px; }
h1 { font-size: 26px; margin: 0 0 8px; }
.description { color: var(--el-text-color-secondary); margin: 0; line-height: 1.7; }
.alert { margin-bottom: 16px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin: 16px 0; }
@media (max-width: 720px) { .models-page { padding: 12px; } .header { flex-direction: column; } }
</style>
