<template>
  <div class="scheduler-page">
    <header class="page-header">
      <div>
        <p class="eyebrow">AUTOMATION / SCHEDULES</p>
        <h1>定时任务计划</h1>
        <p class="subtitle">定义可执行任务，按 Cron 规则定期派发到 Celery Worker；所有执行结果可在自动化任务中查看。</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="reload">刷新</el-button>
    </header>

    <el-alert
      type="info" :closable="false" show-icon class="info-banner"
      title="数据库驱动的定时计划"
      description="保存或启停计划后，Celery Beat 会从数据库同步；生产环境仅运行一个 Beat 实例。此版本只能调度经过后端允许的检测任务。"
    />

    <el-tabs v-model="tab" class="schedule-tabs">
      <el-tab-pane label="定时计划" name="schedules">
        <div class="toolbar">
          <span>共 {{ schedules.length }} 条计划</span>
          <el-button type="primary" :icon="Plus" :disabled="!definitions.length" @click="openSchedule()">
            新建计划
          </el-button>
        </div>
        <el-table :data="schedules" v-loading="loading" row-key="id" stripe>
          <el-table-column prop="name" label="计划名称" min-width="150" show-overflow-tooltip />
          <el-table-column prop="definition_title" label="任务定义" min-width="140" show-overflow-tooltip />
          <el-table-column label="Cron 表达式" min-width="200">
            <template #default="{ row }">
              <code>{{ cronText(row) }}</code>
            </template>
          </el-table-column>
          <el-table-column label="时区" width="125">Asia/Shanghai</el-table-column>
          <el-table-column label="状态" width="115">
            <template #default="{ row }">
              <el-switch :model-value="row.enabled" :loading="busyId === row.id"
                         :disabled="busyId !== null" @change="toggleSchedule(row, $event)" />
            </template>
          </el-table-column>
          <el-table-column label="最近触发" min-width="175">
            <template #default="{ row }">{{ formatDate(row.last_triggered_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="206" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openSchedule(row)">编辑</el-button>
              <el-button link type="success" :loading="busyId === row.id" @click="runNow(row)">立即运行</el-button>
              <el-button link type="danger" @click="removeSchedule(row)">删除</el-button>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty description="暂时没有计划。先创建任务定义，再添加执行时间。" />
          </template>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="任务定义" name="definitions">
        <div class="toolbar">
          <span>共 {{ definitions.length }} 项任务定义</span>
          <el-button type="primary" :icon="Plus" @click="openDefinition()">新建定义</el-button>
        </div>
        <el-table :data="definitions" v-loading="loading" row-key="id" stripe>
          <el-table-column prop="title" label="名称" min-width="180" />
          <el-table-column label="任务类型" min-width="170">
            <template #default="{ row }">{{ typeLabel(row.task_type) }}</template>
          </el-table-column>
          <el-table-column prop="description" label="说明" min-width="230" show-overflow-tooltip />
          <el-table-column label="启用" width="110">
            <template #default="{ row }">
              <el-switch :model-value="row.enabled" :loading="busyId === 'definition-' + row.id"
                         :disabled="busyId !== null" @change="toggleDefinition(row, $event)" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150">
            <template #default="{ row }">
              <el-button link type="primary" @click="openDefinition(row)">编辑</el-button>
              <el-button link type="danger" @click="removeDefinition(row)">删除</el-button>
            </template>
          </el-table-column>
          <template #empty><el-empty description="请先创建一个任务定义" /></template>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="showDefinition" :title="editingDefinition ? '编辑任务定义' : '创建任务定义'"
               width="min(500px, 95vw)" destroy-on-close>
      <el-form :model="definitionForm" :rules="definitionRules" ref="definitionFormRef" label-position="top">
        <el-form-item label="定义名称" prop="title">
          <el-input v-model.trim="definitionForm.title" maxlength="120" show-word-limit />
        </el-form-item>
        <el-form-item label="执行任务类型" prop="task_type">
          <el-select v-model="definitionForm.task_type" style="width:100%">
            <el-option v-for="item in taskTypes" :key="item.value" :value="item.value" :label="item.label" />
          </el-select>
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="definitionForm.description" type="textarea" :rows="2" maxlength="500" show-word-limit />
        </el-form-item>
        <el-form-item label="启用定义">
          <el-switch v-model="definitionForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDefinition = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveDefinition">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showSchedule" :title="editingSchedule ? '编辑定时计划' : '创建定时计划'"
               width="min(660px, 96vw)" destroy-on-close>
      <el-form :model="scheduleForm" ref="scheduleFormRef" :rules="scheduleRules" label-position="top">
        <el-form-item label="计划名称" prop="name">
          <el-input v-model.trim="scheduleForm.name" maxlength="120" show-word-limit />
        </el-form-item>
        <el-form-item label="任务定义" prop="definition">
          <el-select v-model="scheduleForm.definition" placeholder="选择任务定义" style="width:100%">
            <el-option v-for="item in definitions" :key="item.id" :value="item.id"
                       :label="item.title + (item.enabled ? '' : '（已停用）')" :disabled="!item.enabled" />
          </el-select>
        </el-form-item>
        <el-form-item label="快捷计划">
          <el-select v-model="preset" placeholder="自定义 Cron" clearable style="width:100%" @change="applyPreset">
            <el-option label="每 5 分钟" value="five" />
            <el-option label="每天 09:00" value="daily" />
            <el-option label="工作日 09:00" value="weekday" />
            <el-option label="每周一 09:00" value="weekly" />
          </el-select>
        </el-form-item>
        <el-row :gutter="12">
          <el-col v-for="field in cronFields" :key="field.key" :xs="12" :sm="8">
            <el-form-item :label="field.label" :prop="field.key">
              <el-input v-model.trim="scheduleForm[field.key]" :placeholder="field.hint" maxlength="60" />
            </el-form-item>
          </el-col>
        </el-row>
        <div class="cron-preview">
          <strong>Cron：</strong><code>{{ cronText(scheduleForm) }}</code>
          <span>时区 Asia/Shanghai · 星期：0=周日、1=周一、6=周六</span>
        </div>
        <el-form-item label="启用此计划">
          <el-switch v-model="scheduleForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showSchedule = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveSchedule">保存计划</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="taskSchedules">
import { onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Refresh } from "@element-plus/icons-vue";
import {
  listDefinitions, createDefinition, updateDefinition, deleteDefinition,
  listSchedules, createSchedule, updateSchedule, deleteSchedule, runSchedule,
} from "./api";

const tab = ref("schedules");
const loading = ref(false);
const saving = ref(false);
const busyId = ref(null);
const definitions = ref([]);
const schedules = ref([]);
const showDefinition = ref(false);
const showSchedule = ref(false);
const editingDefinition = ref(null);
const editingSchedule = ref(null);
const definitionFormRef = ref(null);
const scheduleFormRef = ref(null);
const preset = ref("");
const taskTypes = [
  { value: "ping", label: "Worker 连通性检测" },
  { value: "database_probe", label: "数据库连通性检测" },
];
const cronFields = [
  { key: "minute", label: "分钟（0–59）", hint: "0 或 */5" },
  { key: "hour", label: "小时（0–23）", hint: "9 或 *" },
  { key: "day_of_month", label: "每月日期（1–31）", hint: "*" },
  { key: "month_of_year", label: "月份（1–12）", hint: "*" },
  { key: "day_of_week", label: "星期（0–6）", hint: "1-5" },
];
const definitionForm = ref({});
const scheduleForm = ref({});
const definitionRules = {
  title: [{ required: true, message: "请输入定义名称", trigger: "blur" }],
  task_type: [{ required: true, message: "请选择已支持的任务", trigger: "change" }],
};
const scheduleRules = {
  name: [{ required: true, message: "请输入计划名称", trigger: "blur" }],
  definition: [{ required: true, message: "请选择任务定义", trigger: "change" }],
  ...Object.fromEntries(cronFields.map((item) => [
    item.key,
    [{ required: true, message: "Cron 字段不能为空", trigger: "blur" }],
  ])),
};

const typeLabel = (value) => taskTypes.find((x) => x.value === value)?.label || value;
const formatDate = (value) => value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
const cronText = (row) => [row.minute, row.hour, row.day_of_month, row.month_of_year, row.day_of_week].join(" ");

async function reload() {
  loading.value = true;
  try {
    const [defs, plans] = await Promise.all([listDefinitions(), listSchedules()]);
    if (defs.code !== 2000 || plans.code !== 2000) throw new Error(defs.msg || plans.msg || "读取失败");
    definitions.value = defs.data || [];
    schedules.value = plans.data || [];
  } catch (error) {
    if (!error?.handled) ElMessage.error(error?.message || "无法加载定时计划");
  } finally {
    loading.value = false;
  }
}

function openDefinition(row = null) {
  editingDefinition.value = row;
  definitionForm.value = row ? {
    title: row.title, task_type: row.task_type, description: row.description, enabled: row.enabled,
  } : { title: "", task_type: "ping", description: "", enabled: true };
  showDefinition.value = true;
}

async function saveDefinition() {
  try { await definitionFormRef.value.validate(); } catch { return; }
  saving.value = true;
  try {
    const result = editingDefinition.value
      ? await updateDefinition(editingDefinition.value.id, definitionForm.value)
      : await createDefinition(definitionForm.value);
    if (result.code !== 2000) throw new Error(result.msg || JSON.stringify(result.errors));
    showDefinition.value = false;
    ElMessage.success("任务定义已保存");
    await reload();
  } catch (error) {
    if (!error?.handled) ElMessage.error(error?.message || "保存失败");
  } finally {
    saving.value = false;
  }
}

function openSchedule(row = null) {
  editingSchedule.value = row;
  preset.value = "";
  scheduleForm.value = row ? {
    name: row.name, definition: row.definition, minute: row.minute, hour: row.hour,
    day_of_month: row.day_of_month, month_of_year: row.month_of_year,
    day_of_week: row.day_of_week, enabled: row.enabled,
  } : {
    name: "", definition: definitions.value.find((x) => x.enabled)?.id ?? null,
    minute: "0", hour: "9", day_of_month: "*",
    month_of_year: "*", day_of_week: "*", enabled: false,
  };
  showSchedule.value = true;
}

function applyPreset(value) {
  const presets = {
    five: ["*/5", "*", "*", "*", "*"],
    daily: ["0", "9", "*", "*", "*"],
    weekday: ["0", "9", "*", "*", "1-5"],
    weekly: ["0", "9", "*", "*", "1"],
  };
  if (!presets[value]) return;
  const [minute, hour, day_of_month, month_of_year, day_of_week] = presets[value];
  Object.assign(scheduleForm.value, { minute, hour, day_of_month, month_of_year, day_of_week });
}

async function saveSchedule() {
  try { await scheduleFormRef.value.validate(); } catch { return; }
  saving.value = true;
  try {
    const result = editingSchedule.value
      ? await updateSchedule(editingSchedule.value.id, scheduleForm.value)
      : await createSchedule(scheduleForm.value);
    if (result.code !== 2000) throw new Error(result.msg || JSON.stringify(result.errors));
    showSchedule.value = false;
    ElMessage.success("计划已保存，Beat 将自动同步");
    await reload();
  } catch (error) {
    if (!error?.handled) ElMessage.error(error?.message || "保存失败");
  } finally {
    saving.value = false;
  }
}

async function toggleSchedule(row, enabled) {
  busyId.value = row.id;
  try {
    const result = await updateSchedule(row.id, { enabled });
    if (result.code !== 2000) throw new Error(result.msg || "状态更新失败");
    await reload();
    ElMessage.success(enabled ? "计划已启用" : "计划已暂停");
  } catch (error) {
    if (!error?.handled) ElMessage.error(error?.message || "切换失败");
  } finally { busyId.value = null; }
}

async function toggleDefinition(row, enabled) {
  busyId.value = "definition-" + row.id;
  try {
    const result = await updateDefinition(row.id, { enabled });
    if (result.code !== 2000) throw new Error(result.msg || "状态更新失败");
    await reload();
    ElMessage.success(enabled ? "定义已启用" : "定义已停用，相关计划同时停发");
  } catch (error) {
    if (!error?.handled) ElMessage.error(error?.message || "切换失败");
  } finally { busyId.value = null; }
}

async function removeSchedule(row) {
  try {
    await ElMessageBox.confirm(`确定删除计划「${row.name}」？这会从 Beat 中移除调度，历史执行记录仍保留。`, "确认删除", { type: "warning" });
  } catch { return; }
  try {
    const result = await deleteSchedule(row.id);
    if (result.code !== 2000) throw new Error(result.msg);
    ElMessage.success("计划已删除");
    await reload();
  } catch (error) { if (!error?.handled) ElMessage.error(error?.message || "删除失败"); }
}

async function removeDefinition(row) {
  try {
    await ElMessageBox.confirm(`删除定义「${row.title}」也会删除其全部定时计划，历史执行记录仍保留。确定吗？`, "确认删除", { type: "warning" });
  } catch { return; }
  try {
    const result = await deleteDefinition(row.id);
    if (result.code !== 2000) throw new Error(result.msg);
    ElMessage.success("定义及其计划已删除");
    await reload();
  } catch (error) { if (!error?.handled) ElMessage.error(error?.message || "删除失败"); }
}

async function runNow(row) {
  busyId.value = row.id;
  try {
    const result = await runSchedule(row.id);
    if (result.code !== 2000) throw new Error(result.msg);
    ElMessage.success("任务已提交，请到「自动化任务」查看执行结果");
  } catch (error) {
    if (!error?.handled) ElMessage.error(error?.message || "提交失败");
  } finally { busyId.value = null; }
}

onMounted(reload);
</script>

<style scoped>
.scheduler-page { max-width: 1560px; padding: 24px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 18px; }
.eyebrow { color: var(--el-color-primary); letter-spacing: .12em; font-size: 12px; font-weight: 700; margin: 0 0 8px; }
h1 { font-size: 27px; margin: 0 0 8px; }
.subtitle { color: var(--el-text-color-secondary); line-height: 1.65; margin: 0; }
.info-banner { margin-bottom: 20px; }
.schedule-tabs { background: var(--el-bg-color); padding: 12px 18px; border-radius: 12px; }
.toolbar { display: flex; align-items: center; justify-content: space-between; color: var(--el-text-color-secondary); margin-bottom: 15px; }
code { font-size: 12px; white-space: nowrap; }
.cron-preview { background: var(--el-fill-color-light); padding: 12px; border-radius: 8px; margin-bottom: 20px; display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
.cron-preview span { font-size: 12px; color: var(--el-text-color-secondary); }
@media (max-width: 760px) {
  .scheduler-page { padding: 12px; }
  .page-header { flex-direction: column; }
  h1 { font-size: 23px; }
  .schedule-tabs { padding: 10px; }
}
</style>
