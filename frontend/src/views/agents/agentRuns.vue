<template>
  <div class="run-page">
    <header class="page-head">
      <div>
        <p class="eyebrow">ENTERPRISE AGENT HUB / RUNTIME</p>
        <h1>Agent 执行中心</h1>
        <p class="subtitle">提交 Agent 分析任务，查看真实执行状态、工具调用步骤与来源。模拟模型不会调用外部 API。</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="reload">刷新</el-button>
    </header>
    <el-alert class="notice" type="info" :closable="false" show-icon
      title="仅支持已发布、已授权的 Agent 与只读工具"
      description="任务异步执行，需要 Redis、Celery Worker 以及 Outbox Dispatcher；使用 Mock Provider 时所有分析数据均为虚构数据。" />
    <el-card shadow="never" class="card">
      <el-form label-position="top" :model="form" class="submit-form" @submit.prevent="submit">
        <el-form-item label="选择 Agent">
          <el-select v-model="form.agent_id" placeholder="请选择已发布 Agent" style="width:100%" filterable>
            <el-option v-for="a in eligibleAgents" :key="a.id" :value="a.id" :label="a.name + ' (' + a.code + ')'" />
          </el-select>
        </el-form-item>
        <el-form-item label="分析任务">
          <el-input v-model="form.message" type="textarea" :rows="3" maxlength="4000" show-word-limit placeholder="例如：分析本月销售情况" />
        </el-form-item>
        <el-button type="primary" :loading="submitting" :disabled="!form.agent_id || !form.message.trim()" @click="submit">提交执行</el-button>
      </el-form>
    </el-card>

    <el-card shadow="never" class="card history">
      <div class="toolbar"><strong>执行历史</strong><span>{{ runs.length }} 条（最近 100 条）</span></div>
      <el-table :data="runs" v-loading="loading" row-key="id" stripe>
        <el-table-column prop="id" label="Run ID" min-width="250" show-overflow-tooltip />
        <el-table-column label="状态" width="115">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="提交时间" min-width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="error_code" label="错误码" min-width="155" show-overflow-tooltip />
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
  <el-button link type="primary" @click="openDetail(row)">详情</el-button>
  <el-button v-if="['QUEUED', 'RUNNING'].includes(row.status)" link type="warning" @click="stopRun(row)">取消</el-button>
</template>
        </el-table-column>
        <template #empty><el-empty description="暂无执行记录" /></template>
      </el-table>
    </el-card>

    <el-drawer v-model="showDetail" title="Agent 执行详情" size="min(700px, 96vw)" @closed="detail = null">
      <template v-if="detail">
        <div class="detail-head">
          <el-tag :type="statusType(detail.status)">{{ statusLabel(detail.status) }}</el-tag>
          <div>
  <el-button v-if="['QUEUED', 'RUNNING'].includes(detail.status)" type="warning" :loading="canceling" @click="stopRun(detail)">取消任务</el-button>
  <el-button :icon="Refresh" :loading="detailLoading" @click="refreshDetail">刷新状态</el-button>
</div>
        </div>
        <el-descriptions border :column="1">
          <el-descriptions-item label="执行 ID"><span class="break">{{ detail.id }}</span></el-descriptions-item>
          <el-descriptions-item label="Agent 版本"><span class="break">{{ detail.agent_version_id }}</span></el-descriptions-item>
          <el-descriptions-item label="开始时间">{{ formatDate(detail.started_at) }}</el-descriptions-item>
          <el-descriptions-item label="结束时间">{{ formatDate(detail.finished_at) }}</el-descriptions-item>
          <el-descriptions-item v-if="detail.error_code" label="失败原因">{{ detail.error_code }}</el-descriptions-item>
        </el-descriptions>
        <h3>分析结果</h3>
        <div v-if="detail.result" class="result">
          <p>{{ detail.result.answer }}</p>
          <small>来源：{{ (detail.result.evidence || []).join("、") || "未提供" }}</small>
          <div v-if="detail.result.mock"><el-tag type="warning">模拟数据，仅用于测试</el-tag></div>
        </div>
        <el-empty v-else description="任务尚未返回结果" />
        <h3>模型用量与估算费用</h3>
        <el-descriptions v-if="usage" border :column="1">
          <el-descriptions-item label="模型">{{ usage.provider }} / {{ usage.model }}</el-descriptions-item>
          <el-descriptions-item label="输入 Token">{{ usage.input_tokens ?? "未知" }}</el-descriptions-item>
          <el-descriptions-item label="输出 Token">{{ usage.output_tokens ?? "未知" }}</el-descriptions-item>
          <el-descriptions-item label="估算费用">{{ usage.estimated_cost === null ? "未知" : '
        <el-timeline>
          <el-timeline-item v-for="s in steps" :key="s.sequence" :timestamp="'步骤 ' + s.sequence">
            <strong>{{ s.kind }}</strong> · {{ s.status }}
            <pre class="json">{{ JSON.stringify(s.details, null, 2) }}</pre>
          </el-timeline-item>
        </el-timeline>
        <h3>运行事件</h3>
        <div v-for="e in events" :key="e.sequence" class="event">
          #{{ e.sequence }} · {{ e.type }}
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup name="agentRuns">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Refresh } from "@element-plus/icons-vue";
import { listAgents, listRuns, createRun, getRun, getRunSteps, getRunEvents, cancelRun, getRunUsage } from "./api";

const agents = ref([]);
const runs = ref([]);
const form = ref({ agent_id: "", message: "分析本月销售情况" });
const loading = ref(false);
const submitting = ref(false);
const detailLoading = ref(false);
const showDetail = ref(false);
const detail = ref(null);
const steps = ref([]);
const events = ref([]);
const usage = ref(null);
const canceling = ref(false);
let timer = null;
const eligibleAgents = computed(() => agents.value.filter(a => a.status === "active"));
const statusType = s => ({ QUEUED: "info", RUNNING: "primary", SUCCEEDED: "success", FAILED: "danger", CANCEL_REQUESTED: "warning", CANCELLED: "warning" }[s] || "info");
const statusLabel = s => ({ QUEUED: "待执行", RUNNING: "执行中", SUCCEEDED: "已成功", FAILED: "已失败", CANCEL_REQUESTED: "取消中", CANCELLED: "已取消" }[s] || s);
const formatDate = s => s ? new Date(s).toLocaleString("zh-CN", { hour12: false }) : "—";
const pending = computed(() => runs.value.some(r => ["QUEUED", "RUNNING", "CANCEL_REQUESTED"].includes(r.status)));

async function reload() {
  if (loading.value) return;
  loading.value = true;
  try {
    const [a, r] = await Promise.all([listAgents(), listRuns()]);
    if (a.code !== 2000 || r.code !== 2000) throw new Error(a.msg || r.msg || "加载失败");
    agents.value = a.data || [];
    runs.value = r.data || [];
  } catch (e) { ElMessage.error(e?.message || "加载执行记录失败"); }
  finally { loading.value = false; }
}
async function submit() {
  if (!form.value.agent_id || !form.value.message.trim()) return;
  submitting.value = true;
  try {
    const idempotencyKey = crypto.randomUUID();
    const r = await createRun({
      agent_id: form.value.agent_id, input: { message: form.value.message }, deadline_seconds: 120,
    }, idempotencyKey);
    if (r.code !== 2000) throw new Error(r.msg || r.error?.message || "提交失败");
    ElMessage.success("任务已创建，等待 Worker 执行");
    await reload();
    await openDetail(r.data);
  } catch (e) { ElMessage.error(e?.message || "任务提交失败"); }
  finally { submitting.value = false; }
}
async function openDetail(row) {
  detail.value = row;
  showDetail.value = true;
  await refreshDetail();
}
async function refreshDetail() {
  if (!detail.value || detailLoading.value) return;
  detailLoading.value = true;
  try {
    const id = detail.value.id;
    const [run, s, e, u] = await Promise.all([getRun(id), getRunSteps(id), getRunEvents(id), getRunUsage(id)]);
    if ([run, s, e, u].some(x => x.code !== 2000)) throw new Error("获取执行详情失败");
    detail.value = run.data;
    steps.value = s.data || [];
    events.value = e.data || [];
    usage.value = u.data;
  } catch (err) { ElMessage.error(err?.message || "读取详情失败"); }
  finally { detailLoading.value = false; }
}
async function stopRun(row) {
  try {
    await ElMessageBox.confirm("取消操作仅在安全检查点生效，无法立即中断已发送的模型请求。确定取消？", "取消 AgentRun", { type: "warning" });
  } catch { return; }
  canceling.value = true;
  try {
    const response = await cancelRun(row.id);
    if (response.code !== 2000) throw new Error(response.msg || "取消失败");
    ElMessage.success("取消请求已提交");
    await reload();
    if (showDetail.value && detail.value?.id === row.id) await refreshDetail();
  } catch (error) { ElMessage.error(error?.message || "取消失败"); }
  finally { canceling.value = false; }
}
onMounted(() => {
  reload();
  timer = window.setInterval(() => {
    if (document.visibilityState !== "visible") return;
    if (pending.value) reload();
    if (showDetail.value && ["QUEUED", "RUNNING", "CANCEL_REQUESTED"].includes(detail.value?.status)) refreshDetail();
  }, 4000);
});
onUnmounted(() => { if (timer) window.clearInterval(timer); });
</script>

<style scoped>
.run-page { padding: 24px; max-width: 1480px; margin: 0 auto; }
.page-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 20px; }
.eyebrow { font-size: 12px; font-weight: 700; letter-spacing: .1em; color: var(--el-color-primary); margin: 0 0 8px; }
h1 { font-size: 27px; margin: 0 0 8px; }
.subtitle { color: var(--el-text-color-secondary); margin: 0; line-height: 1.7; }
.notice { margin-bottom: 18px; }
.card { border-radius: 12px; margin-bottom: 18px; }
.submit-form { max-width: 720px; }
.toolbar { display: flex; justify-content: space-between; margin-bottom: 16px; color: var(--el-text-color-secondary); }
.detail-head { display: flex; justify-content: space-between; margin-bottom: 15px; }
.break { overflow-wrap: anywhere; }
.result, .json { background: var(--el-fill-color-light); padding: 12px; border-radius: 8px; overflow-wrap: anywhere; white-space: pre-wrap; }
.usage-note { color: var(--el-text-color-secondary); font-size: 12px; }
.event { padding: 8px 0; border-bottom: 1px solid var(--el-border-color-light); }
@media (max-width: 760px) { .run-page { padding: 12px; } .page-head { flex-direction: column; } }
</style>
 + usage.estimated_cost + ' USD' }}</el-descriptions-item>
        </el-descriptions>
        <el-empty v-else description="暂无模型用量记录" />
        <p class="usage-note">估算费用仅供参考，不代表供应商实际账单。</p>
        <h3>执行步骤</h3>
        <el-timeline>
          <el-timeline-item v-for="s in steps" :key="s.sequence" :timestamp="'步骤 ' + s.sequence">
            <strong>{{ s.kind }}</strong> · {{ s.status }}
            <pre class="json">{{ JSON.stringify(s.details, null, 2) }}</pre>
          </el-timeline-item>
        </el-timeline>
        <h3>运行事件</h3>
        <div v-for="e in events" :key="e.sequence" class="event">
          #{{ e.sequence }} · {{ e.type }}
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup name="agentRuns">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Refresh } from "@element-plus/icons-vue";
import { listAgents, listRuns, createRun, getRun, getRunSteps, getRunEvents, cancelRun, getRunUsage } from "./api";

const agents = ref([]);
const runs = ref([]);
const form = ref({ agent_id: "", message: "分析本月销售情况" });
const loading = ref(false);
const submitting = ref(false);
const detailLoading = ref(false);
const showDetail = ref(false);
const detail = ref(null);
const steps = ref([]);
const events = ref([]);
const usage = ref(null);
const canceling = ref(false);
let timer = null;
const eligibleAgents = computed(() => agents.value.filter(a => a.status === "active"));
const statusType = s => ({ QUEUED: "info", RUNNING: "primary", SUCCEEDED: "success", FAILED: "danger", CANCEL_REQUESTED: "warning", CANCELLED: "warning" }[s] || "info");
const statusLabel = s => ({ QUEUED: "待执行", RUNNING: "执行中", SUCCEEDED: "已成功", FAILED: "已失败", CANCEL_REQUESTED: "取消中", CANCELLED: "已取消" }[s] || s);
const formatDate = s => s ? new Date(s).toLocaleString("zh-CN", { hour12: false }) : "—";
const pending = computed(() => runs.value.some(r => ["QUEUED", "RUNNING", "CANCEL_REQUESTED"].includes(r.status)));

async function reload() {
  if (loading.value) return;
  loading.value = true;
  try {
    const [a, r] = await Promise.all([listAgents(), listRuns()]);
    if (a.code !== 2000 || r.code !== 2000) throw new Error(a.msg || r.msg || "加载失败");
    agents.value = a.data || [];
    runs.value = r.data || [];
  } catch (e) { ElMessage.error(e?.message || "加载执行记录失败"); }
  finally { loading.value = false; }
}
async function submit() {
  if (!form.value.agent_id || !form.value.message.trim()) return;
  submitting.value = true;
  try {
    const idempotencyKey = crypto.randomUUID();
    const r = await createRun({
      agent_id: form.value.agent_id, input: { message: form.value.message }, deadline_seconds: 120,
    }, idempotencyKey);
    if (r.code !== 2000) throw new Error(r.msg || r.error?.message || "提交失败");
    ElMessage.success("任务已创建，等待 Worker 执行");
    await reload();
    await openDetail(r.data);
  } catch (e) { ElMessage.error(e?.message || "任务提交失败"); }
  finally { submitting.value = false; }
}
async function openDetail(row) {
  detail.value = row;
  showDetail.value = true;
  await refreshDetail();
}
async function refreshDetail() {
  if (!detail.value || detailLoading.value) return;
  detailLoading.value = true;
  try {
    const id = detail.value.id;
    const [run, s, e, u] = await Promise.all([getRun(id), getRunSteps(id), getRunEvents(id), getRunUsage(id)]);
    if ([run, s, e, u].some(x => x.code !== 2000)) throw new Error("获取执行详情失败");
    detail.value = run.data;
    steps.value = s.data || [];
    events.value = e.data || [];
    usage.value = u.data;
  } catch (err) { ElMessage.error(err?.message || "读取详情失败"); }
  finally { detailLoading.value = false; }
}
onMounted(() => {
  reload();
  timer = window.setInterval(() => {
    if (document.visibilityState !== "visible") return;
    if (pending.value) reload();
    if (showDetail.value && ["QUEUED", "RUNNING", "CANCEL_REQUESTED"].includes(detail.value?.status)) refreshDetail();
  }, 4000);
});
onUnmounted(() => { if (timer) window.clearInterval(timer); });
</script>

<style scoped>
.run-page { padding: 24px; max-width: 1480px; margin: 0 auto; }
.page-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 20px; }
.eyebrow { font-size: 12px; font-weight: 700; letter-spacing: .1em; color: var(--el-color-primary); margin: 0 0 8px; }
h1 { font-size: 27px; margin: 0 0 8px; }
.subtitle { color: var(--el-text-color-secondary); margin: 0; line-height: 1.7; }
.notice { margin-bottom: 18px; }
.card { border-radius: 12px; margin-bottom: 18px; }
.submit-form { max-width: 720px; }
.toolbar { display: flex; justify-content: space-between; margin-bottom: 16px; color: var(--el-text-color-secondary); }
.detail-head { display: flex; justify-content: space-between; margin-bottom: 15px; }
.break { overflow-wrap: anywhere; }
.result, .json { background: var(--el-fill-color-light); padding: 12px; border-radius: 8px; overflow-wrap: anywhere; white-space: pre-wrap; }
.event { padding: 8px 0; border-bottom: 1px solid var(--el-border-color-light); }
@media (max-width: 760px) { .run-page { padding: 12px; } .page-head { flex-direction: column; } }
</style>
