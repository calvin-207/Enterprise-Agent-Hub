<template>
  <div class="chat-workspace">
    <aside class="sidebar">
      <div class="side-title"><strong>Agent 会话</strong><el-button size="small" type="primary" :icon="Plus" @click="newConversation">新会话</el-button></div>
      <el-select v-model="agentId" placeholder="选择 Agent" style="width:100%" @change="loadSessions">
        <el-option v-for="a in agents.filter(a => a.status === 'active')" :key="a.id" :label="a.name" :value="a.id"/>
      </el-select>
      <div class="side-scroll">
        <el-empty v-if="sessions.length === 0" description="暂无会话" :image-size="65"/>
        <div v-for="session in sessions" :key="session.id" class="session-item" :class="{ active: session.id === selected?.id }" @click="selectSession(session)">
          <div class="session-name">{{ session.title }}</div>
          <small>{{ session.active_run_id ? '执行中' : '已保存' }} · {{ dateFmt(session.updated_at) }}</small>
        </div>
      </div>
      <div v-if="selected" class="side-footer">
        <el-button size="small" @click="rename">重命名</el-button>
        <el-button size="small" type="warning" plain @click="archive">归档</el-button>
      </div>
    </aside>
    <main class="main-panel">
      <header class="chat-header">
        <div><h2>{{ selected?.title || "选择会话，开始使用 Agent" }}</h2>
          <p>Agent 消息和执行状态持久保存；模拟模型使用虚构销售数据，不代表真实经营情况。</p></div>
        <el-button :icon="Refresh" @click="refreshMessages" :disabled="!selected">刷新</el-button>
      </header>
      <div class="message-list" ref="messageArea">
        <el-empty v-if="!selected" description="在左侧选择 Agent 并创建会话"/>
        <el-empty v-else-if="messages.length === 0" description="开始向 Agent 提问"/>
        <div v-for="m in messages" :key="m.id" class="message" :class="m.role">
          <div class="role">{{ m.role === 'user' ? '你' : 'Agent' }}</div>
          <p>{{ m.content }}</p>
          <small>{{ dateFmt(m.created_at) }}</small>
        </div>
        <div v-if="activeRun" class="running-state">
          <el-icon class="is-loading"><Loading /></el-icon>
          {{ runStatus(activeRun.status) }}
          <el-button v-if="['QUEUED','RUNNING'].includes(activeRun.status)" link type="warning" @click="cancelActive">取消任务</el-button>
          <div v-if="eventLog.length" class="events">{{ eventLog.slice(-5).map(x => '#' + x.sequence + ' ' + x.type).join(' · ') }}</div>
        </div>
      </div>
      <div class="composer">
        <el-input v-model="draft" type="textarea" :rows="3" maxlength="4000" show-word-limit
          :disabled="!selected || !!activeRun" placeholder="例如：分析一下10月销售情况，然后继续追问9月数据"
          @keydown.ctrl.enter.prevent="send"/>
        <div class="compose-actions">
          <small>Ctrl + Enter 发送 · 单会话串行执行 · 断线后可继续查看</small>
          <el-button type="primary" :loading="sending" :disabled="!selected || !!activeRun || !draft.trim()" @click="send">发送</el-button>
        </div>
      </div>
    </main>
  </div>
</template>
<script setup name="agentChat">
import { ref, nextTick, onMounted, onUnmounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Refresh, Loading } from "@element-plus/icons-vue";
import {
  listAgents, listSessions, createSession, getSession, updateSession,
  getSessionMessages, submitSessionRun, getRun, getRunEvents, cancelRun,
} from "./api";
import { streamRunEvents } from "./stream";

const agents = ref([]), agentId = ref(""), sessions = ref([]), selected = ref(null);
const messages = ref([]), draft = ref(""), activeRun = ref(null), eventLog = ref([]);
const sending = ref(false), messageArea = ref(null);
let aborted = null, generation = 0;
const dateFmt = value => value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
const runStatus = s => ({ QUEUED: "任务排队中", RUNNING: "Agent 正在执行", CANCEL_REQUESTED: "取消请求已提交" }[s] || s);
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

function stopStream() {
  generation += 1;
  aborted?.abort();
  aborted = null;
  activeRun.value = null;
  eventLog.value = [];
}
async function initialize() {
  try {
    const result = await listAgents();
    if (result.code !== 2000) throw Error(result.msg);
    agents.value = result.data || [];
    agentId.value = agents.value.find(x => x.status === "active")?.id || "";
    if (agentId.value) await loadSessions();
  } catch (error) { if (!error?.handled) ElMessage.error(error?.message || "加载 Agent 失败"); }
}
async function loadSessions() {
  stopStream(); selected.value = null; messages.value = [];
  try {
    const result = await listSessions();
    if (result.code !== 2000) throw Error(result.msg);
    sessions.value = (result.data || []).filter(s => s.agent_id === agentId.value);
    if (sessions.value.length) await selectSession(sessions.value[0]);
  } catch (error) { if (!error?.handled) ElMessage.error(error?.message || "加载会话失败"); }
}
async function newConversation() {
  if (!agentId.value) return ElMessage.warning("请先选择 Agent");
  try {
    const answer = await createSession({ agent_id: agentId.value, title: "新会话" });
    if (answer.code !== 2000) throw Error(answer.msg);
    await loadSessions();
    await selectSession(answer.data);
  } catch (error) { if (!error?.handled) ElMessage.error(error?.message || "创建会话失败"); }
}
async function selectSession(session) {
  stopStream();
  selected.value = session;
  await refreshMessages();
  // Read latest active run from DB to resume after reload or a network outage.
  try {
    const result = await getSession(session.id);
    if (result.code === 2000 && selected.value?.id === session.id) {
      selected.value = result.data;
      if (result.data.active_run_id) void watchRun(result.data.active_run_id);
    }
  } catch { /* next manual refresh can recover */ }
}
async function refreshMessages() {
  if (!selected.value) return;
  try {
    // Always read from cursor zero for convergence after disconnection.
    const response = await getSessionMessages(selected.value.id, 0);
    if (response.code !== 2000) throw Error(response.msg);
    messages.value = response.data || [];
    await nextTick();
    if (messageArea.value) messageArea.value.scrollTop = messageArea.value.scrollHeight;
  } catch (error) { if (!error?.handled) ElMessage.error(error?.message || "读取消息失败"); }
}
async function send() {
  if (!selected.value || activeRun.value || !draft.value.trim()) return;
  const message = draft.value.trim(), sid = selected.value.id;
  sending.value = true;
  try {
    const response = await submitSessionRun(sid, message, crypto.randomUUID());
    if (response.code !== 2000) throw Error(response.error?.message || response.msg);
    draft.value = "";
    await refreshMessages();
    void watchRun(response.data.id);
  } catch (error) { if (!error?.handled) ElMessage.error(error?.message || "提交任务失败"); }
  finally { sending.value = false; }
}
async function watchRun(id) {
  aborted?.abort();
  const controller = new AbortController();
  aborted = controller;
  const myGeneration = ++generation;
  let cursor = 0;
  activeRun.value = { id, status: "QUEUED" };
  eventLog.value = [];
  while (!controller.signal.aborted && myGeneration === generation) {
    try {
      await streamRunEvents(id, cursor, event => {
        if (myGeneration !== generation) return;
        if (event.sequence <= cursor) return;
        cursor = event.sequence;
        eventLog.value.push(event);
      }, { signal: controller.signal });
    } catch (e) {
      if (controller.signal.aborted) break;
      // SSE is optional at the edge; REST cursor provides lossless recovery.
      try {
        const response = await getRunEvents(id);
        for (const ev of (response.data || [])) {
          if (ev.sequence > cursor) { cursor = ev.sequence; eventLog.value.push(ev); }
        }
      } catch { /* retry bounded through existing run status */ }
    }
    if (myGeneration !== generation || controller.signal.aborted) break;
    try {
      const result = await getRun(id);
      if (result.code !== 2000) break;
      activeRun.value = result.data;
      if (["SUCCEEDED", "FAILED", "CANCELLED"].includes(result.data.status)) {
        if (result.data.status === "FAILED") ElMessage.warning("执行失败：" + result.data.error_code);
        await refreshMessages();
        if (selected.value) {
          const s = await getSession(selected.value.id);
          if (s.code === 2000) selected.value = s.data;
        }
        break;
      }
    } catch { /* reconnect after transient errors */ }
    await delay(1000);
  }
  if (myGeneration === generation) { activeRun.value = null; aborted = null; }
}
async function cancelActive() {
  if (!activeRun.value) return;
  try {
    await ElMessageBox.confirm("运行中取消是协作式操作，无法撤回已发送的模型请求。确定取消？", "取消会话任务", { type: "warning" });
    await cancelRun(activeRun.value.id);
  } catch { /* user cancelled confirmation */ }
}
async function rename() {
  if (!selected.value) return;
  try {
    const { value } = await ElMessageBox.prompt("会话名称", "重命名", { inputValue: selected.value.title, inputValidator: x => !!x?.trim() && x.length <= 120 });
    const r = await updateSession(selected.value.id, { title: value });
    if (r.code !== 2000) throw Error(r.msg);
    selected.value = r.data;
    sessions.value = sessions.value.map(x => x.id === r.data.id ? r.data : x);
  } catch { /* dismissed */ }
}
async function archive() {
  if (!selected.value || activeRun.value) return;
  try {
    await ElMessageBox.confirm("归档后会话只读，历史记录仍保留。继续？", "归档会话", { type: "warning" });
    const r = await updateSession(selected.value.id, { archived: true });
    if (r.code !== 2000) throw Error(r.msg);
    await loadSessions();
  } catch { /* dismissed */ }
}
onMounted(initialize);
onUnmounted(stopStream);
</script>
<style scoped>
.chat-workspace { display: flex; gap: 0; height: calc(100vh - 160px); min-height: 540px; border: 1px solid var(--el-border-color-light); border-radius: 12px; overflow: hidden; margin: 16px; background: var(--el-bg-color); }
.sidebar { width: 274px; flex: 0 0 274px; padding: 16px; border-right: 1px solid var(--el-border-color-light); display: flex; flex-direction: column; gap: 12px; background: var(--el-fill-color-lighter); }
.side-title, .side-footer, .compose-actions { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.side-scroll { min-height: 0; overflow-y: auto; flex: 1; }
.session-item { cursor: pointer; border-radius: 8px; padding: 12px 10px; margin-bottom: 6px; }
.session-item:hover, .session-item.active { background: var(--el-color-primary-light-9); }
.session-name { font-size: 14px; font-weight: 600; overflow-wrap: anywhere; }
.session-item small, .compose-actions small { color: var(--el-text-color-secondary); }
.main-panel { display: flex; min-width: 0; flex: 1; flex-direction: column; }
.chat-header { padding: 20px 24px; border-bottom: 1px solid var(--el-border-color-light); }
.chat-header h2 { margin: 0 0 8px; font-size: 21px; }
.chat-header p { margin: 0; color: var(--el-text-color-secondary); font-size: 12px; }
.message-list { flex: 1; overflow-y: auto; padding: 20px 24px; }
.message { max-width: 86%; margin: 0 0 18px; padding: 14px 16px; border-radius: 10px; background: var(--el-fill-color-light); overflow-wrap: anywhere; }
.message.user { margin-left: auto; background: var(--el-color-primary-light-9); }
.message .role { font-size: 12px; font-weight: 700; margin-bottom: 6px; color: var(--el-color-primary); }
.message p { margin: 0 0 8px; white-space: pre-wrap; line-height: 1.65; }
.message small { color: var(--el-text-color-secondary); }
.running-state { color: var(--el-color-primary); font-size: 13px; margin: 12px 0; }
.events { margin-top: 8px; color: var(--el-text-color-secondary); font-size: 11px; }
.composer { padding: 16px 24px; border-top: 1px solid var(--el-border-color-light); }
.compose-actions { margin-top: 10px; }
@media (max-width: 800px) { .chat-workspace { margin: 8px; } .sidebar { width: 185px; flex-basis: 185px; } .message-list, .composer { padding: 12px; } }
</style>
