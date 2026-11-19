<template>
  <div class="ops-page">
    <header class="header">
      <div>
        <p class="eyebrow">ENTERPRISE AGENT HUB / OPERATIONS</p>
        <h1>运维管理</h1>
        <p class="description">
          汇总主机资源、数据库、Redis、Celery Worker 与 Beat 的运行状态，及时发现阻塞、超时与容量隐患；可下钻查看节点详情与系统日志。
        </p>
      </div>
      <div class="actions">
        <template v-if="activeTab === 'overview'">
          <el-select v-model="intervalSec" :disabled="!autoRefresh" style="width: 104px" aria-label="刷新间隔">
            <el-option :value="10" label="10 秒" />
            <el-option :value="30" label="30 秒" />
            <el-option :value="60" label="60 秒" />
          </el-select>
          <el-switch v-model="autoRefresh" active-text="自动刷新" />
          <el-button type="primary" :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
        </template>
      </div>
    </header>

    <el-tabs v-model="activeTab" class="ops-tabs">
      <!-- ======================== 运行概览 ======================== -->
      <el-tab-pane label="运行概览" name="overview">
        <el-alert
          v-if="overview"
          :type="overallType"
          show-icon
          :closable="false"
          class="alert"
          :title="overallTitle"
        >
          <div v-if="overview.risks.length" class="risks">
            <p v-for="risk in overview.risks" :key="risk">• {{ risk }}</p>
          </div>
        </el-alert>
        <el-alert
          v-else-if="loadError"
          type="error"
          show-icon
          :closable="false"
          class="alert"
          title="运行状态获取失败"
          :description="loadError"
        />

        <div v-if="overview" class="server-bar">
          <span v-for="item in serverChips" :key="item.label" class="chip">
            <span class="chip-k">{{ item.label }}</span>
            <span class="chip-v" :title="item.value">{{ item.value }}</span>
          </span>
        </div>

        <el-row v-if="overview" :gutter="16" class="cards">
          <el-col v-for="card in overview.components" :key="card.key" :xs="24" :sm="12" :lg="8">
            <el-card shadow="hover" class="ops-card" :class="'is-' + card.status">
              <div class="card-head">
                <span class="card-icon"><el-icon :size="18"><component :is="iconOf(card.key)" /></el-icon></span>
                <h3>{{ card.title }}</h3>
                <el-tag :type="tagType(card.status)" size="small" effect="light" class="card-tag">
                  {{ statusLabel(card.status) }}
                </el-tag>
              </div>

              <p class="card-message">{{ card.message }}</p>

              <el-progress
                v-if="card.percent !== undefined && card.percent !== null"
                class="card-meter"
                :percentage="card.percent"
                :color="meterColor(card.status)"
                :stroke-width="10"
                :show-text="true"
              />

              <ul v-if="card.metrics && card.metrics.length" class="kv">
                <li v-for="metric in card.metrics" :key="metric.label">
                  <span class="k">{{ metric.label }}</span>
                  <span class="v">{{ metric.value }}</span>
                </li>
              </ul>

              <div v-if="card.key === 'celery_worker' && card.workers && card.workers.length" class="workers">
                <button
                  v-for="worker in card.workers"
                  :key="worker.name"
                  type="button"
                  class="worker-row"
                  title="点击查看节点详情"
                  @click="openWorkerDetail(worker.name)"
                >
                  <el-icon :size="14" :color="worker.alive ? '#67C23A' : '#F56C6C'">
                    <CircleCheckFilled v-if="worker.alive" />
                    <CircleCloseFilled v-else />
                  </el-icon>
                  <span class="worker-name">{{ worker.name }}</span>
                  <span class="worker-meta">
                    并发 {{ worker.concurrency ?? "—" }} · 心跳 {{ formatHeartbeat(worker) }}<template v-if="worker.env"> · {{ formatWorkerIdentity(worker) }}</template>
                  </span>
                  <el-icon class="worker-arrow" :size="12"><ArrowRight /></el-icon>
                  <el-tooltip
                    v-if="workerMismatched(worker, card)"
                    :content="`该 Worker 与当前服务环境/版本不一致（服务：${serviceMetric(card, '本服务环境') ?? '—'} ${serviceMetric(card, '本服务版本') ?? ''}），存在串环境或旧版本消费风险`"
                  >
                    <el-tag size="small" type="warning" effect="plain">不匹配</el-tag>
                  </el-tooltip>
                </button>
              </div>
            </el-card>
          </el-col>
        </el-row>

        <footer v-if="overview" class="foot">
          数据采集于 {{ overview.server.time }}；告警阈值：CPU ≥75% 注意 / ≥90% 异常，内存、磁盘 ≥80% 注意 / ≥90% 异常，心跳超时 180 秒。点击 Worker 节点可查看详情。
        </footer>
      </el-tab-pane>

      <!-- ======================== 系统日志 ======================== -->
      <el-tab-pane label="系统日志" name="logs" lazy>
        <div class="log-toolbar">
          <el-select
            v-model="logFile"
            filterable
            placeholder="选择日志文件"
            style="width: 300px"
            :loading="logFilesLoading"
            @change="loadLogs"
          >
            <el-option
              v-for="file in logFiles"
              :key="file.name"
              :label="`${file.name}（${file.size_text}）`"
              :value="file.name"
            >
              <span class="log-option-name">{{ file.name }}</span>
              <span class="log-option-meta">{{ file.size_text }} · {{ file.mtime }}</span>
            </el-option>
          </el-select>
          <el-select v-model="logLines" style="width: 108px" aria-label="读取行数" @change="loadLogs">
            <el-option :value="100" label="100 行" />
            <el-option :value="200" label="200 行" />
            <el-option :value="500" label="500 行" />
          </el-select>
          <el-input
            v-model="logQuery"
            clearable
            placeholder="按关键字过滤行（如 ERROR）"
            prefix-icon="Search"
            style="width: 240px"
          />
          <el-button type="primary" :icon="Refresh" :loading="logLoading" :disabled="!logFile" @click="loadLogs">
            刷新
          </el-button>
        </div>
        <p v-if="logData.file" class="log-meta">
          {{ logData.file.name }} · {{ logData.file.size_text }} · 更新于 {{ logData.file.mtime }}
          · 显示 {{ filteredLogLines.length }}/{{ logData.lines.length }} 行（从文件末尾读取，最多 500 行）
        </p>
        <div v-loading="logLoading" class="log-viewer">
          <div v-if="!logLoading && !filteredLogLines.length" class="log-empty">
            {{ logFile ? "没有匹配关键字的日志行" : "请选择日志文件" }}
          </div>
          <pre v-else>{{ filteredLogLines.join("\n") }}</pre>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- ======================== Worker 详情抽屉 ======================== -->
    <el-drawer v-model="workerDrawer" :title="workerDetail?.name || '节点详情'" size="min(600px, 94vw)">
      <div v-loading="workerLoading" class="worker-detail">
        <template v-if="workerDetail">
          <div class="worker-detail-status">
            <el-tag :type="workerDetail.online ? 'success' : 'danger'" effect="light">
              {{ workerDetail.online ? "在线" : "离线 / 无响应" }}
            </el-tag>
            <el-tag v-if="workerDetail.env" type="info" effect="plain">环境 {{ workerDetail.env }}</el-tag>
            <el-tag v-if="workerDetail.version" type="info" effect="plain">版本 {{ workerDetail.version }}</el-tag>
            <span class="worker-detail-hb">心跳 {{ formatHeartbeat(workerDetail) }}</span>
          </div>

          <el-alert
            v-if="!workerDetail.online"
            type="warning"
            show-icon
            :closable="false"
            title="节点未响应实时探测"
            description="该 Worker 可能已停止或长时间阻塞。若心跳仍在刷新说明进程仍在执行心跳任务；否则请检查进程。"
            class="worker-alert"
          />

          <el-descriptions v-if="workerDetail.online" :column="1" border size="small" class="worker-desc">
            <el-descriptions-item label="并发数">{{ workerDetail.concurrency ?? "未知" }}</el-descriptions-item>
            <el-descriptions-item label="Worker PID">{{ workerDetail.pid ?? "未知" }}</el-descriptions-item>
            <el-descriptions-item label="进程池 PID">
              {{ workerDetail.processes?.length ? workerDetail.processes.join("、") : "未知" }}
            </el-descriptions-item>
            <el-descriptions-item label="已运行">{{ formatUptime(workerDetail.uptime_seconds) }}</el-descriptions-item>
            <el-descriptions-item label="累计执行任务">{{ workerDetail.total_tasks ?? 0 }} 次</el-descriptions-item>
            <el-descriptions-item label="待执行（预留队列）">{{ workerDetail.reserved_count }}</el-descriptions-item>
            <el-descriptions-item label="定时等待（ETA）">{{ workerDetail.scheduled_count }}</el-descriptions-item>
            <el-descriptions-item label="已注册任务">{{ workerDetail.registered_count }} 个</el-descriptions-item>
          </el-descriptions>

          <template v-if="workerDetail.online && workerDetail.top_tasks?.length">
            <h4 class="worker-section">高频任务 Top</h4>
            <ul class="kv">
              <li v-for="[task, count] in workerDetail.top_tasks" :key="task">
                <span class="k">{{ task }}</span>
                <span class="v">{{ count }} 次</span>
              </li>
            </ul>
          </template>

          <h4 class="worker-section">正在执行（{{ workerDetail.active_count }}）</h4>
          <el-table
            v-if="workerDetail.active?.length"
            :data="workerDetail.active"
            size="small"
            stripe
          >
            <el-table-column prop="name" label="任务" min-width="180" show-overflow-tooltip />
            <el-table-column prop="args" label="参数" min-width="140" show-overflow-tooltip />
            <el-table-column prop="time_start" label="开始时间" min-width="140" />
            <el-table-column prop="worker_pid" label="PID" width="70" />
          </el-table>
          <p v-else class="worker-idle">空闲，没有正在执行的任务。</p>
        </template>
        <div v-else-if="!workerLoading" class="log-empty">未获取到节点数据</div>

        <div class="worker-detail-actions">
          <el-button :icon="Refresh" :loading="workerLoading" @click="loadWorkerDetail">刷新</el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onActivated, onBeforeUnmount, onDeactivated, ref, watch } from "vue";
import {
  AlarmClock,
  ArrowRight,
  CircleCheckFilled,
  CircleCloseFilled,
  Connection,
  Coin,
  Cpu,
  Folder,
  Histogram,
  Odometer,
  Refresh,
} from "@element-plus/icons-vue";
import Api from "@/api/api";

const activeTab = ref("overview");
const overview = ref(null);
const loading = ref(false);
const loadError = ref("");
const autoRefresh = ref(true);
const intervalSec = ref(30);

// ---------------- 系统日志 ----------------
const logFiles = ref([]);
const logFile = ref("");
const logLines = ref(200);
const logQuery = ref("");
const logLoading = ref(false);
const logFilesLoading = ref(false);
const logData = ref({ file: null, lines: [] });
let logsInitiated = false;

const filteredLogLines = computed(() => {
  const lines = logData.value.lines || [];
  const keyword = logQuery.value.trim().toLowerCase();
  if (!keyword) return lines;
  return lines.filter((line) => line.toLowerCase().includes(keyword));
});

async function loadLogFiles(preselect = true) {
  logFilesLoading.value = true;
  try {
    const res = await Api.apiSystemOpsLogs();
    if (res.code == 2000) {
      logFiles.value = res.data.files || [];
      if (preselect && !logFile.value && logFiles.value.length) {
        logFile.value = logFiles.value[0].name;
        await loadLogs();
      }
    }
  } finally {
    logFilesLoading.value = false;
  }
}

async function loadLogs() {
  if (!logFile.value || logLoading.value) return;
  logLoading.value = true;
  try {
    const res = await Api.apiSystemOpsLogs({ file: logFile.value, lines: logLines.value });
    if (res.code == 2000) {
      logData.value = res.data;
    }
  } finally {
    logLoading.value = false;
  }
}

// ---------------- Worker 详情 ----------------
const workerDrawer = ref(false);
const workerLoading = ref(false);
const workerDetail = ref(null);
const workerDetailName = ref("");

async function loadWorkerDetail() {
  if (!workerDetailName.value || workerLoading.value) return;
  workerLoading.value = true;
  try {
    const res = await Api.apiSystemOpsWorkerDetail({ name: workerDetailName.value });
    if (res.code == 2000) {
      workerDetail.value = res.data;
    }
  } finally {
    workerLoading.value = false;
  }
}

function openWorkerDetail(name) {
  workerDetailName.value = name;
  workerDetail.value = null;
  workerDrawer.value = true;
  loadWorkerDetail();
}

const formatUptime = (seconds) => {
  if (seconds === null || seconds === undefined) return "未知";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h) return `${h} 小时 ${m} 分`;
  if (m) return `${m} 分 ${Math.floor(seconds % 60)} 秒`;
  return `${Math.floor(seconds)} 秒`;
};

const CARD_ICONS = {
  cpu: Cpu,
  memory: Odometer,
  disk: Folder,
  database: Coin,
  redis: Connection,
  celery_worker: Histogram,
  celery_beat: AlarmClock,
};

// Element Plus 语义色（状态色仅用于状态，且始终伴随文字标签出现）
const STATUS_COLORS = { ok: "#67C23A", warn: "#E6A23C", error: "#F56C6C" };
const STATUS_LABELS = { ok: "正常", warn: "注意", error: "异常" };
const STATUS_TAGS = { ok: "success", warn: "warning", error: "danger" };

const iconOf = (key) => CARD_ICONS[key] || Coin;
const statusLabel = (status) => STATUS_LABELS[status] || status;
const tagType = (status) => STATUS_TAGS[status] || "info";
const meterColor = (status) => STATUS_COLORS[status] || STATUS_COLORS.error;

const overallType = computed(() => STATUS_TAGS[overview.value?.overall?.status] || "info");
const overallTitle = computed(() => {
  const overall = overview.value?.overall;
  if (!overall) return "";
  const parts = [`正常 ${overall.ok_count} 项`];
  if (overall.warn_count) parts.push(`注意 ${overall.warn_count} 项`);
  if (overall.error_count) parts.push(`异常 ${overall.error_count} 项`);
  const headline =
    overall.status === "ok"
      ? "平台各组件运行正常"
      : overall.status === "warn"
        ? "平台整体可用，存在需要关注的隐患"
        : "存在异常组件，请立即排查";
  return `${headline}（共 7 项：${parts.join("，")}）`;
});

const serverChips = computed(() => {
  const server = overview.value?.server;
  if (!server) return [];
  const chips = [
    { label: "主机", value: server.hostname },
    { label: "操作系统", value: server.platform },
    { label: "Python", value: server.python },
    { label: "Django", value: server.django },
    { label: "服务器时间", value: server.time },
  ];
  if (server.process) {
    chips.push({
      label: "API 进程",
      value: `PID ${server.process.pid} · 已运行 ${server.process.uptime} · 内存 ${server.process.memory}`,
    });
  }
  return chips;
});

const formatHeartbeat = (worker) => {
  if (!worker.last_heartbeat) return "未上报";
  const age = worker.heartbeat_age;
  const ageText = age === null ? "" : `（${age < 60 ? `${age} 秒前` : `${Math.floor(age / 60)} 分钟前`}）`;
  return `${worker.last_heartbeat}${ageText}`;
};

// Worker 心跳上报的环境与版本（旧版 Worker 未上报时不展示）
const formatWorkerIdentity = (worker) => `环境 ${worker.env ?? "—"} · 版本 ${worker.version ?? "—"}`;

const serviceMetric = (card, label) =>
  card?.metrics?.find((metric) => metric.label === label)?.value;

const workerMismatched = (worker, card) => {
  if (!worker.env) return false;
  const env = serviceMetric(card, "本服务环境");
  const version = serviceMetric(card, "本服务版本");
  if (!env) return false;
  return worker.env !== env || (worker.version && version && worker.version !== version);
};

async function load() {
  if (loading.value) return;
  loading.value = true;
  loadError.value = "";
  try {
    const res = await Api.apiSystemOpsOverview();
    if (res.code == 2000) {
      overview.value = res.data;
    } else {
      loadError.value = res.msg || "接口返回异常";
    }
  } catch (error) {
    loadError.value = error?.message || "网络错误，无法获取运行状态";
  } finally {
    loading.value = false;
  }
}

let timer = null;
function restartTimer() {
  if (timer) clearInterval(timer);
  timer = null;
  if (autoRefresh.value && activeTab.value === "overview") {
    timer = setInterval(() => {
      if (!document.hidden) load();
    }, intervalSec.value * 1000);
  }
}

// 概览轮询只在概览 Tab 激活时进行；日志 Tab 首次进入时加载文件列表
watch([autoRefresh, intervalSec, activeTab], (values, oldValues) => {
  restartTimer();
  if (activeTab.value === "logs" && !logsInitiated) {
    logsInitiated = true;
    loadLogFiles();
  }
  if (activeTab.value === "overview" && oldValues?.[2] === "logs") {
    load();
  }
});
onActivated(() => {
  load();
  restartTimer();
});
onDeactivated(() => {
  if (timer) clearInterval(timer);
  timer = null;
});
onBeforeUnmount(() => {
  if (timer) clearInterval(timer);
  timer = null;
});

load();
restartTimer();
</script>

<style scoped>
.ops-page {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
  color: var(--el-text-color-primary);
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.eyebrow {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.12em;
  color: var(--el-color-primary);
}
.header h1 {
  margin: 0 0 8px;
  font-size: 28px;
  font-weight: 650;
}
.description {
  margin: 0;
  line-height: 1.7;
  color: var(--el-text-color-secondary);
  max-width: 640px;
}
.actions {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 32px;
}
.alert {
  margin-bottom: 16px;
}
.risks p {
  margin: 2px 0;
  line-height: 1.7;
}
.server-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  padding: 10px 16px;
  margin-bottom: 16px;
  border-radius: 10px;
  background: var(--el-fill-color-light);
  font-size: 12px;
}
.chip {
  display: inline-flex;
  gap: 6px;
  align-items: baseline;
  max-width: 100%;
}
.chip-k {
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}
.chip-v {
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cards { row-gap: 16px; }
.ops-card {
  height: 100%;
  border-radius: 12px;
  border-top: 3px solid transparent;
}
.ops-card.is-ok { border-top-color: var(--el-color-success); }
.ops-card.is-warn { border-top-color: var(--el-color-warning); }
.ops-card.is-error { border-top-color: var(--el-color-danger); }
.card-head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.card-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 9px;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.card-head h3 {
  margin: 0;
  font-size: 15px;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card-message {
  margin: 12px 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);
  min-height: 21px;
}
.card-meter { margin-bottom: 12px; }
.kv {
  list-style: none;
  margin: 0;
  padding: 0;
  font-size: 13px;
}
.kv li {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 5px 0;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
.kv li:last-child { border-bottom: none; }
.kv .k {
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kv .v {
  color: var(--el-text-color-primary);
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.workers {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.worker-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 4px;
  font-size: 13px;
  font-family: inherit;
  text-align: left;
  background: transparent;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  color: inherit;
}
.worker-row:hover,
.worker-row:focus-visible {
  background: var(--el-fill-color-light);
  outline: none;
}
.worker-name {
  font-weight: 600;
}
.worker-meta {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.worker-arrow {
  color: var(--el-text-color-placeholder);
  flex-shrink: 0;
}
.foot {
  margin-top: 16px;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  line-height: 1.7;
}

/* ---------------- 系统日志 ---------------- */
.log-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-bottom: 10px;
}
.log-option-name { float: left; }
.log-option-meta {
  float: right;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.log-meta {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.log-viewer {
  min-height: 260px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  background: var(--el-fill-color-light);
  padding: 12px 14px;
}
.log-viewer pre {
  margin: 0;
  font-family: Consolas, "Courier New", monospace;
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--el-text-color-primary);
  max-height: 60vh;
  overflow: auto;
}
.log-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 220px;
  color: var(--el-text-color-placeholder);
  font-size: 13px;
}

/* ---------------- Worker 详情抽屉 ---------------- */
.worker-detail { display: block; }
.worker-detail-status {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.worker-detail-hb {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.worker-alert { margin-bottom: 12px; }
.worker-desc { margin-bottom: 12px; }
.worker-section {
  margin: 16px 0 8px;
  font-size: 14px;
  color: var(--el-text-color-primary);
}
.worker-idle {
  margin: 4px 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.worker-detail-actions {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
@media (max-width: 767px) {
  .ops-page { padding: 12px; }
  .header h1 { font-size: 24px; }
  .log-toolbar .el-select { width: 100% !important; }
}
</style>
