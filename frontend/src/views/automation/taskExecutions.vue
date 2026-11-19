<template>
  <div class="automation-page">
    <div class="page-header">
      <div>
        <p class="eyebrow">AUTOMATION / EXECUTIONS</p>
        <h1>自动化任务</h1>
        <p class="subtitle">查看后台任务执行情况，验证 Worker、Redis 和数据库服务。生产业务任务将在接入后出现在这里。</p>
      </div>
      <div class="header-actions">
        <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
        <el-button type="primary" :icon="Plus" @click="showCreate = true">发起检测任务</el-button>
      </div>
    </div>

    <el-row :gutter="12" class="summary-row">
      <el-col v-for="item in summaryItems" :key="item.value" :xs="12" :sm="6">
        <el-card shadow="never" class="stat">
          <div class="stat-label">{{ item.label }}</div>
          <div class="stat-value">{{ counts[item.value] ?? 0 }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="content-card">
      <div class="filters">
        <div class="filter-title">执行记录 <el-tag effect="plain" type="info">{{ total }} 条</el-tag></div>
        <el-select v-model="statusFilter" placeholder="全部状态" clearable style="width: 160px" @change="applyFilter">
          <el-option v-for="item in summaryItems" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
      </div>

      <el-table :data="rows" v-loading="loading" row-key="id" class="tasks-table" stripe>
        <el-table-column prop="id" label="编号" width="90" />
        <el-table-column prop="title" label="任务名称" min-width="180" show-overflow-tooltip />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_by_name" label="发起人" min-width="110" />
        <el-table-column label="提交时间" min-width="175">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="完成时间" min-width="175">
          <template #default="{ row }">{{ formatDate(row.finished_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="175" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">详情</el-button>
            <el-button link type="warning" :disabled="row.status !== 'failed' || submitting" @click="retry(row)">重试</el-button>
          </template>
        </el-table-column>
        <template #empty><el-empty description="暂无任务记录，可先发起一次检测任务" /></template>
      </el-table>
      <div class="pagination">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="limit"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          background
          @current-change="load"
          @size-change="onSizeChange"
        />
      </div>
    </el-card>

    <el-dialog v-model="showCreate" title="发起检测任务" width="min(460px, 94vw)">
      <el-form label-position="top">
        <el-form-item label="任务类型">
          <el-select v-model="newTaskType" style="width:100%">
            <el-option label="Worker 连通性检测" value="ping" />
            <el-option label="数据库连通性检测" value="database_probe" />
          </el-select>
        </el-form-item>
      </el-form>
      <el-alert type="info" :closable="false" title="仅可执行预定义、无破坏性的检测任务。任务会由 Celery Worker 异步处理。" />
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">提交任务</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="showDetail" title="任务执行详情" size="min(560px, 95vw)" @closed="detail = null">
      <template v-if="detail">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="编号">{{ detail.id }}</el-descriptions-item>
          <el-descriptions-item label="任务名称">{{ detail.title }}</el-descriptions-item>
          <el-descriptions-item label="任务状态">
            <el-tag :type="statusType(detail.status)">{{ statusText(detail.status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="发起人">{{ detail.created_by_name }}</el-descriptions-item>
          <el-descriptions-item label="Celery Task ID"><span class="word-break">{{ detail.celery_task_id }}</span></el-descriptions-item>
          <el-descriptions-item label="重试来源">{{ detail.retry_of ?? "—" }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatDate(detail.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="开始时间">{{ formatDate(detail.started_at) }}</el-descriptions-item>
          <el-descriptions-item label="完成时间">{{ formatDate(detail.finished_at) }}</el-descriptions-item>
        </el-descriptions>
        <h3>执行结果</h3>
        <pre class="result-block">{{ formatResult(detail.result) }}</pre>
        <template v-if="detail.error_message">
          <h3>错误说明</h3>
          <el-alert :title="detail.error_message" type="error" :closable="false" show-icon />
        </template>
        <div class="drawer-actions">
          <el-button :loading="detailLoading" :icon="Refresh" @click="refreshDetail">刷新状态</el-button>
          <el-button v-if="detail.status === 'failed'" type="warning" :loading="submitting" @click="retry(detail)">重试任务</el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup name="taskExecutions">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Refresh } from "@element-plus/icons-vue";
import { listExecutions, getExecution, createExecution, retryExecution } from "./api";

const page = ref(1);
const limit = ref(10);
const statusFilter = ref("");
const rows = ref([]);
const total = ref(0);
const counts = ref({});
const loading = ref(false);
const detailLoading = ref(false);
const submitting = ref(false);
const showCreate = ref(false);
const newTaskType = ref("ping");
const showDetail = ref(false);
const detail = ref(null);
let pollTimer = null;

const summaryItems = [
  { value: "queued", label: "排队中" },
  { value: "running", label: "执行中" },
  { value: "success", label: "已成功" },
  { value: "failed", label: "已失败" },
];

const statusMap = Object.fromEntries(summaryItems.map((item) => [item.value, item.label]));
const statusText = (value) => statusMap[value] || value;
const statusType = (value) => ({ queued: "info", running: "primary", success: "success", failed: "danger" }[value] || "info");
const formatDate = (value) => value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
const formatResult = (value) => value == null ? "暂无结果" : JSON.stringify(value, null, 2);
const hasPending = computed(() => rows.value.some((row) => ["queued", "running"].includes(row.status)));

async function load() {
  if (loading.value) return;
  loading.value = true;
  try {
    const response = await listExecutions({ page: page.value, limit: limit.value, status: statusFilter.value });
    if (response.code !== 2000) throw new Error(response.msg || "获取任务失败");
    rows.value = response.data.data || [];
    total.value = response.data.total || 0;
    counts.value = response.data.counts || {};
  } catch (error) {
    if (!error?.handled) ElMessage.error(error?.message || "获取任务列表失败");
  } finally {
    loading.value = false;
  }
}

function applyFilter() {
  page.value = 1;
  load();
}
function onSizeChange() {
  page.value = 1;
  load();
}
async function submit() {
  submitting.value = true;
  try {
    const response = await createExecution(newTaskType.value);
    if (response.code !== 2000) throw new Error(response.msg || "提交失败");
    showCreate.value = false;
    page.value = 1;
    statusFilter.value = "";
    ElMessage.success("任务已提交，请关注执行状态");
    await load();
  } catch (error) {
    if (!error?.handled) ElMessage.error(error?.message || "提交任务失败");
  } finally {
    submitting.value = false;
  }
}
async function retry(row) {
  try {
    await ElMessageBox.confirm(`确定重新执行任务 #${row.id}？这将创建一条新的执行记录。`, "确认重试", { type: "warning" });
  } catch {
    return;
  }
  submitting.value = true;
  try {
    const response = await retryExecution(row.id);
    if (response.code !== 2000) throw new Error(response.msg || "重试失败");
    ElMessage.success("已创建新的重试任务");
    showDetail.value = false;
    page.value = 1;
    statusFilter.value = "";
    await load();
  } catch (error) {
    if (!error?.handled) ElMessage.error(error?.message || "重试失败");
  } finally {
    submitting.value = false;
  }
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
    const response = await getExecution(detail.value.id);
    if (response.code !== 2000) throw new Error(response.msg || "获取详情失败");
    detail.value = response.data;
  } catch (error) {
    if (!error?.handled) ElMessage.error(error?.message || "刷新详情失败");
  } finally {
    detailLoading.value = false;
  }
}

onMounted(() => {
  load();
  pollTimer = window.setInterval(() => {
    if (document.visibilityState === "visible" && (hasPending.value || (detail.value && ["queued", "running"].includes(detail.value.status)))) {
      load();
      if (showDetail.value) refreshDetail();
    }
  }, 5000);
});
onUnmounted(() => {
  if (pollTimer) window.clearInterval(pollTimer);
});
</script>

<style scoped>
.automation-page { padding: 24px; max-width: 1600px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 20px; }
.eyebrow { font-size: 12px; letter-spacing: 0.12em; font-weight: 700; color: var(--el-color-primary); margin: 0 0 8px; }
.page-header h1 { font-size: 27px; margin: 0 0 7px; }
.subtitle { color: var(--el-text-color-secondary); margin: 0; line-height: 1.6; }
.header-actions { display: flex; flex-shrink: 0; gap: 6px; }
.summary-row { row-gap: 12px; margin-bottom: 18px; }
.stat { border-radius: 12px; }
.stat-label { color: var(--el-text-color-secondary); font-size: 13px; margin-bottom: 10px; }
.stat-value { font-size: 28px; font-weight: 700; }
.content-card { border-radius: 12px; }
.filters { display: flex; gap: 12px; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.filter-title { font-size: 16px; font-weight: 600; display: flex; align-items: center; gap: 10px; }
.pagination { display: flex; justify-content: flex-end; padding-top: 18px; overflow-x: auto; }
.result-block { padding: 14px; border-radius: 10px; white-space: pre-wrap; overflow-wrap: anywhere; background: var(--el-fill-color-light); color: var(--el-text-color-primary); }
.word-break { overflow-wrap: anywhere; }
.drawer-actions { margin-top: 20px; display: flex; gap: 10px; }
@media (max-width: 720px) {
  .automation-page { padding: 12px; }
  .page-header { flex-direction: column; }
  .header-actions { flex-wrap: wrap; }
  .page-header h1 { font-size: 23px; }
}
</style>
