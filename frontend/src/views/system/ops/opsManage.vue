<template>
  <div class="ops-page">
    <header class="header">
      <div>
        <p class="eyebrow">ENTERPRISE AGENT HUB / OPERATIONS</p>
        <h1>运维管理</h1>
        <p class="description">
          汇总主机资源、数据库、Redis、Celery Worker 与 Beat 的运行状态，及时发现阻塞、超时与容量隐患；可下钻节点详情、实时尾随系统日志。
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
        <template v-else-if="activeTab === 'logs'">
          <el-select
            v-if="logStreamState === 'polling'"
            v-model="logIntervalSec"
            style="width: 104px"
            aria-label="日志轮询间隔"
          >
            <el-option :value="5" label="5 秒" />
            <el-option :value="10" label="10 秒" />
            <el-option :value="30" label="30 秒" />
          </el-select>
          <el-switch v-model="logAutoRefresh" active-text="实时跟随" />
          <el-button
            type="primary"
            :icon="Refresh"
            :loading="logLoading"
            :disabled="!logFile"
            @click="reloadCurrentLog"
          >
            刷新
          </el-button>
        </template>
      </div>
    </header>

    <el-tabs v-model="activeTab" class="ops-tabs">
      <!-- ======================== 运行概览 ======================== -->
      <el-tab-pane label="运行概览" name="overview">
        <div class="tab-scroll">
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
          <el-col v-for="card in displayCards" :key="card.key" :xs="24" :sm="12" :lg="8">
            <el-card shadow="hover" class="ops-card" :class="'is-' + card.status">
              <div class="card-head">
                <span class="card-icon"><el-icon :size="18"><component :is="iconOf(card.key)" /></el-icon></span>
                <h3 :title="card.title">{{ card.title }}</h3>
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

              <!-- 单节点：Worker 信息内嵌在汇总卡里 -->
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
                <div v-if="logKeywordOf(card.key)" class="card-actions">
                  <el-button link type="success" size="small" :icon="Document" @click.stop="viewLogs(logKeywordOf(card.key))">
                    日志查看
                  </el-button>
                </div>
              </div>

              <!-- Worker 汇总卡（多节点时不含内嵌列表）与其它卡片：按需提供日志入口 -->
              <div
                v-else-if="logKeywordOf(card.key) && !(card.key === 'celery_worker' && card.workers && card.workers.length)"
                class="card-actions"
              >
                <el-button
                  v-if="card.key !== 'celery_worker'"
                  link
                  type="success"
                  size="small"
                  :icon="Document"
                  @click.stop="viewLogs(logKeywordOf(card.key))"
                >
                  日志查看
                </el-button>
              </div>

              <!-- Worker 节点卡（多节点拆分）：节点级操作 -->
              <div v-if="card.isWorkerNode" class="card-actions worker-node-actions">
                <el-button link type="primary" size="small" @click="openWorkerDetail(card.worker.name)">
                  节点详情
                </el-button>
                <el-button link type="success" size="small" :icon="Document" @click.stop="viewLogs('worker')">
                  日志查看
                </el-button>
                <el-tooltip
                  v-if="nodeMismatched(card.worker)"
                  content="该 Worker 与当前服务环境/版本不一致，存在串环境或旧版本消费风险"
                >
                  <el-tag size="small" type="warning" effect="plain">不匹配</el-tag>
                </el-tooltip>
              </div>
            </el-card>
          </el-col>
        </el-row>

        <footer v-if="overview" class="foot">
          数据采集于 {{ overview.server.time }}；告警阈值：CPU ≥75% 注意 / ≥90% 异常，内存、磁盘 ≥80% 注意 / ≥90% 异常，心跳超时 180 秒。点击 Worker 节点可查看详情，多个节点会拆分为独立卡片。
        </footer>
        </div>
      </el-tab-pane>

      <!-- ======================== 系统日志 ======================== -->
      <el-tab-pane label="系统日志" name="logs" lazy>
        <div class="logs-pane">
        <div class="log-toolbar">
          <el-select
            v-model="logFile"
            filterable
            placeholder="选择日志文件"
            style="width: 300px"
            :loading="logFilesLoading"
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
          <el-select
            v-model="logLines"
            style="width: 108px"
            aria-label="读取行数"
            :disabled="isStreaming"
            @change="loadLogs"
          >
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
        </div>
        <p v-if="logData.file" class="log-meta">
          <span class="stream-dot" :class="logStreamState" aria-hidden="true"></span>
          {{ streamStateText }} · {{ logMetaText }}
        </p>
        <div v-loading="logLoading" class="log-viewer">
          <div v-if="!logLoading && !filteredLogLines.length" class="log-empty">
            {{ logFile ? "没有匹配关键字的日志行" : "请选择日志文件" }}
          </div>
          <pre v-else ref="logPre">{{ filteredLogLines.join("\n") }}</pre>
        </div>
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
import { computed, nextTick, onActivated, onBeforeUnmount, onDeactivated, ref, watch } from "vue";
import {
  AlarmClock,
  ArrowRight,
  CircleCheckFilled,
  CircleCloseFilled,
  Connection,
  Coin,
  Cpu,
  Document,
  Folder,
  Histogram,
  Odometer,
  Platform,
  Refresh,
} from "@element-plus/icons-vue";
import Api from "@/api/api";
import { getToken } from "@/utils/util";
import sysConfig from "@/config";

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
const logAutoRefresh = ref(true);
const logIntervalSec = ref(10);
// off 未开启 | connecting 连接中 | live 流式跟随中 | polling 降级轮询
const logStreamState = ref("off");
const logPre = ref(null);
let logsInitiated = false;
let logSocket = null;
let logTimer = null;
let pendingLogKeyword = "";

const isStreaming = computed(() => ["connecting", "live"].includes(logStreamState.value));

const streamStateText = computed(() => ({
  off: "自动跟随未开启",
  connecting: "正在建立实时连接…",
  live: "实时跟随中（tail -f，仅推送新增行）",
  polling: "轮询模式（实时连接不可用，已自动降级）",
}[logStreamState.value] || ""));

const logMetaText = computed(() => {
  if (!logData.value.file) return "";
  const file = logData.value.file;
  const sizeText = file.size_text && file.size_text !== "—" ? ` · ${file.size_text}` : "";
  const mtimeText = file.mtime && file.mtime !== "实时" ? ` · 更新于 ${file.mtime}` : "";
  return `${file.name}${sizeText}${mtimeText} · 显示 ${filteredLogLines.value.length}/${logData.value.lines.length} 行`;
});

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
        await selectLogFile(pendingLogKeyword || logFiles.value[0].name);
      }
    }
  } finally {
    logFilesLoading.value = false;
  }
}

/** 按文件名精确 → 模糊包含 → server.log 兜底 选中并加载日志 */
async function selectLogFile(keyword) {
  const files = logFiles.value;
  if (!files.length) return;
  const lower = String(keyword || "").toLowerCase();
  const target =
    files.find((f) => f.name.toLowerCase() === lower) ||
    files.find((f) => f.name.toLowerCase().includes(lower)) ||
    files.find((f) => f.name.toLowerCase() === "server.log");
  if (!target) return;
  if (target.name === logFile.value) {
    await reloadCurrentLog();
  } else {
    logFile.value = target.name; // watch(logFile) 统一接管加载/重连
  }
}

async function reloadCurrentLog() {
  if (isStreaming.value) {
    startLogStream(); // 流式模式下“刷新”= 重连（重发 init 上下文）
  } else {
    await loadLogs();
  }
}

async function loadLogs() {
  if (!logFile.value || logLoading.value) return;
  logLoading.value = true;
  const pinned = isPinnedToBottom();
  try {
    const res = await Api.apiSystemOpsLogs({ file: logFile.value, lines: logLines.value });
    if (res.code == 2000) {
      logData.value = res.data;
    }
  } finally {
    logLoading.value = false;
  }
  await scrollToBottomIfPinned(pinned);
}

// ---------------- 实时跟随（tail -f，WebSocket） ----------------

function isPinnedToBottom() {
  const el = logPre.value;
  return el ? el.scrollHeight - el.scrollTop - el.clientHeight < 40 : true;
}

async function scrollToBottomIfPinned(pinned) {
  if (!pinned) return;
  await nextTick();
  if (logPre.value) logPre.value.scrollTop = logPre.value.scrollHeight;
}

function buildLogSocketUrl() {
  const token = getToken();
  if (!token || !logFile.value) return null;
  const host = sysConfig.API_HOST;
  const origin = new URL(
    host.startsWith("http") ? host : window.location.protocol + "//" + host,
    window.location.origin,
  );
  origin.protocol = origin.protocol === "https:" ? "wss:" : "ws:";
  origin.pathname = "/ws/ops/logs/";
  origin.search = `?file=${encodeURIComponent(logFile.value)}`;
  return origin.toString();
}

function stopLogStream() {
  const socket = logSocket;
  logSocket = null;
  if (socket) {
    socket.onclose = null;
    socket.onmessage = null;
    try {
      socket.close();
    } catch (error) {
      /* 忽略关闭异常 */
    }
  }
}

function startLogStream() {
  stopLogStream();
  const url = buildLogSocketUrl();
  if (!url) {
    logStreamState.value = "polling";
    restartLogTimer();
    return;
  }
  logStreamState.value = "connecting";
  const socket = new WebSocket(url, ["JWTLEEADMIN", `JWTlee${getToken()}`]);
  logSocket = socket;
  socket.onopen = () => {
    if (logSocket !== socket) return;
    logStreamState.value = "live";
    if (logTimer) clearInterval(logTimer);
    logTimer = null;
  };
  socket.onmessage = (event) => {
    if (logSocket !== socket) return;
    let message;
    try {
      message = JSON.parse(event.data);
    } catch (error) {
      return;
    }
    handleStreamMessage(message);
  };
  socket.onclose = () => {
    if (logSocket !== socket) return;
    logSocket = null;
    // 主动开启中掉线：自动降级轮询；开关已关/离开页面则保持 off
    if (logAutoRefresh.value && activeTab.value === "logs") {
      logStreamState.value = "polling";
      restartLogTimer();
    } else {
      logStreamState.value = "off";
    }
  };
  socket.onerror = () => {
    /* 统一由 onclose 处理降级 */
  };
}

function handleStreamMessage(message) {
  if (message.type === "init") {
    logData.value = {
      file: { name: message.file, size_text: "—", mtime: "实时" },
      lines: message.lines || [],
    };
    scrollToBottomIfPinned(true);
  } else if (message.type === "lines") {
    const merged = [...(logData.value.lines || []), ...(message.lines || [])].slice(-500);
    logData.value = { ...logData.value, lines: merged };
    scrollToBottomIfPinned(isPinnedToBottom());
  } else if (message.type === "rotated" || message.type === "notice") {
    const merged = [...(logData.value.lines || []), `── ${message.message} ──`].slice(-500);
    logData.value = { ...logData.value, lines: merged };
  } else if (message.type === "error") {
    stopLogStream();
    logStreamState.value = "polling";
    restartLogTimer();
  }
}

// ---------------- 概览 → 日志快速定位 ----------------

/** 各卡片对应的日志文件关键词：worker/beat 进程日志，Django 侧问题看 server.log */
function logKeywordOf(key) {
  if (key === "celery_worker" || String(key).startsWith("worker:")) return "worker";
  if (key === "celery_beat") return "beat";
  if (key === "main_service" || key === "database" || key === "redis") return "server";
  return null;
}

async function viewLogs(keyword) {
  pendingLogKeyword = keyword;
  activeTab.value = "logs";
  if (!logFiles.value.length) {
    logsInitiated = true;
    await loadLogFiles(false);
    if (!logFile.value && logFiles.value.length) {
      await selectLogFile(keyword);
    }
  } else if (logFile.value) {
    await selectLogFile(keyword);
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

// ---------------- 概览渲染 ----------------

const CARD_ICONS = {
  main_service: Platform,
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

const iconOf = (key) => CARD_ICONS[String(key).split(":")[0]] || Histogram;
const statusLabel = (status) => STATUS_LABELS[status] || status;
const tagType = (status) => STATUS_TAGS[status] || "info";
const meterColor = (status) => STATUS_COLORS[status] || STATUS_COLORS.error;

/** 多 Worker 时把每个节点拆成独立卡片；单 Worker 保持内嵌展示 */
const displayCards = computed(() => {
  const cards = [];
  for (const card of overview.value?.components || []) {
    if (card.key === "celery_worker" && card.workers && card.workers.length > 1) {
      const { workers, ...summary } = card;
      cards.push(summary);
      for (const worker of workers) {
        cards.push(workerNodeCard(worker, card));
      }
    } else {
      cards.push(card);
    }
  }
  return cards;
});

function workerNodeCard(worker, summaryCard) {
  const stale = worker.alive && worker.heartbeat_age !== null && worker.heartbeat_age !== undefined && worker.heartbeat_age > 180;
  const status = !worker.alive ? "error" : stale ? "warn" : "ok";
  const stateText = !worker.alive ? "离线或无响应" : stale ? "在线但心跳超时" : "在线";
  const identity = worker.env ? `环境 ${worker.env} / 版本 ${worker.version ?? "—"}` : "未上报环境信息";
  return {
    key: `worker:${worker.name}`,
    title: worker.name,
    status,
    isWorkerNode: true,
    worker,
    message: `${stateText}，并发 ${worker.concurrency ?? "未知"}`,
    metrics: [
      { label: "状态", value: stateText },
      { label: "并发", value: String(worker.concurrency ?? "未知") },
      { label: "最近心跳", value: worker.last_heartbeat || "未上报" },
      { label: "环境 / 版本", value: identity },
      { label: "汇总卡状态", value: `${summaryCard.title}：${summaryCard.message}` },
    ],
  };
}

const nodeMismatched = (worker) => {
  const env = overview.value?.components?.find((c) => c.key === "celery_worker");
  if (!env || !worker.env) return false;
  return workerMismatched(worker, env);
};

const overallType = computed(() => STATUS_TAGS[overview.value?.overall?.status] || "info");
const overallTitle = computed(() => {
  const overall = overview.value?.overall;
  if (!overall) return "";
  const parts = [`正常 ${overall.ok_count} 项`];
  if (overall.warn_count) parts.push(`注意 ${overall.warn_count} 项`);
  if (overall.error_count) parts.push(`异常 ${overall.error_count} 项`);
  const nodeCount = displayCards.value.length - (overview.value?.components?.length || 0);
  const suffix = nodeCount > 0 ? `，Worker 拆分为 ${nodeCount} 个节点卡` : "";
  const headline =
    overall.status === "ok"
      ? "平台各组件运行正常"
      : overall.status === "warn"
        ? "平台整体可用，存在需要关注的隐患"
        : "存在异常组件，请立即排查";
  return `${headline}（${parts.join("，")}${suffix}）`;
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

// ---------------- 定时器与生命周期 ----------------

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

function restartLogTimer() {
  if (logTimer) clearInterval(logTimer);
  logTimer = null;
  if (
    logAutoRefresh.value &&
    activeTab.value === "logs" &&
    logFile.value &&
    !isStreaming.value
  ) {
    logTimer = setInterval(() => {
      if (!document.hidden) loadLogs();
    }, logIntervalSec.value * 1000);
  }
}

// 概览轮询只在概览 Tab 激活时进行；日志跟随按开关/文件变化建立或降级
watch([autoRefresh, intervalSec, activeTab], (_values, oldValues) => {
  restartTimer();
  if (activeTab.value === "logs") {
    if (!logsInitiated) {
      logsInitiated = true;
      loadLogFiles();
    } else if (logAutoRefresh.value && logFile.value && logStreamState.value === "off") {
      startLogStream(); // 回到日志 Tab 时恢复跟随
    }
  } else if (oldValues?.[2] === "logs") {
    stopLogStream();
    logStreamState.value = "off";
    restartLogTimer();
    load();
  }
});

// 开关变化：优先走流式；不可用自动降级轮询（onclose / onerror 处理）
watch([logAutoRefresh, logIntervalSec], () => {
  if (!logAutoRefresh.value) {
    stopLogStream();
    logStreamState.value = "off";
  } else if (activeTab.value === "logs" && logFile.value && logStreamState.value !== "live" && logStreamState.value !== "connecting") {
    startLogStream();
  }
  restartLogTimer();
});

// 切换文件：流式下重连（init 重新提供上下文），否则 HTTP 拉取
watch(logFile, (name) => {
  if (!name) return;
  pendingLogKeyword = "";
  if (logAutoRefresh.value && activeTab.value === "logs") {
    startLogStream();
  } else {
    loadLogs();
  }
  restartLogTimer();
});

onActivated(() => {
  load();
  restartTimer();
  restartLogTimer();
});
onDeactivated(() => {
  if (timer) clearInterval(timer);
  if (logTimer) clearInterval(logTimer);
  stopLogStream();
  logStreamState.value = "off";
  timer = logTimer = null;
});
onBeforeUnmount(() => {
  if (timer) clearInterval(timer);
  if (logTimer) clearInterval(logTimer);
  stopLogStream();
  timer = logTimer = null;
});

load();
restartTimer();
</script>

<style scoped>
/* 页面高度托管：占满 lee-panel-main（flex:1 + overflow:auto 的布局滚动容器），
   页面自身不再产生整页滚动条；滚动收敛到各 Tab 内部的单一区域 */
.ops-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
  color: var(--el-text-color-primary);
}
.ops-tabs {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.ops-tabs :deep(.el-tabs__header) {
  margin-bottom: 16px;
  flex-shrink: 0;
}
.ops-tabs :deep(.el-tabs__content) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.ops-tabs :deep(.el-tab-pane) {
  height: 100%;
  min-height: 0;
}
/* 概览 Tab：内容整体在此区域滚动 */
.tab-scroll {
  height: 100%;
  min-height: 0;
  overflow-y: auto;
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
.card-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.worker-node-actions { justify-content: flex-end; }
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
.logs-pane {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.log-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-bottom: 10px;
  flex-shrink: 0;
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
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 6px;
}
.stream-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  background: var(--el-text-color-placeholder);
}
.stream-dot.live { background: var(--el-color-success); }
.stream-dot.connecting { background: var(--el-color-warning); }
.stream-dot.polling { background: var(--el-color-warning); }
/* 日志框占满剩余高度，滚动只发生在框内（本 Tab 唯一滚动区域） */
.log-viewer {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  background: var(--el-fill-color-light);
  padding: 12px 14px;
  box-sizing: border-box;
}
.log-viewer pre {
  flex: 1;
  min-height: 0;
  margin: 0;
  font-family: Consolas, "Courier New", monospace;
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--el-text-color-primary);
  overflow: auto;
}
.log-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 160px;
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
