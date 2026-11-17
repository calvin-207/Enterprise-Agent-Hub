<template>
  <div class="hub-home">
    <header class="hub-header">
      <p class="hub-eyebrow">ENTERPRISE AGENT HUB</p>
      <h1>工作台</h1>
      <p class="hub-lead">欢迎进入企业 Agent 管理平台。先完成组织、权限和平台基础设置，再逐步启用 Agent 业务能力。</p>
    </header>

    <el-alert
      title="Agent 运行、工具接入和人工审批仍在建设中"
      description="当前版本提供已实现的账户、组织、权限、日志及消息管理功能。尚未上线的 Agent 功能不会出现在菜单中。"
      type="info"
      :closable="false"
      show-icon
      class="hub-notice"
    />

    <h2>开始使用</h2>
    <el-row :gutter="16" class="hub-grid">
      <el-col v-for="item in shortcuts" :key="item.path" :xs="24" :sm="12" :lg="8">
        <router-link :to="item.path" class="hub-link">
          <el-card shadow="hover" class="hub-card">
            <div class="hub-card-top">
              <el-icon :size="24"><component :is="item.icon" /></el-icon>
              <el-icon><ArrowRight /></el-icon>
            </div>
            <h3>{{ item.title }}</h3>
            <p>{{ item.description }}</p>
          </el-card>
        </router-link>
      </el-col>
    </el-row>

    <p class="hub-footnote">以上入口对应当前系统已有的页面，具体操作仍由后端角色及数据权限控制。</p>
  </div>
</template>

<script setup>
import {
  ArrowRight,
  User,
  OfficeBuilding,
  Lock,
  Setting,
  Document,
  Message,
} from "@element-plus/icons-vue";

const shortcuts = [
  { title: "用户管理", description: "维护平台账户、登录状态和人员信息", path: "/buserManage", icon: User },
  { title: "部门管理", description: "维护组织结构及数据归属", path: "/deptManage", icon: OfficeBuilding },
  { title: "权限管理", description: "为角色配置菜单、接口和字段权限", path: "/authorityManage", icon: Lock },
  { title: "平台设置", description: "配置平台名称及常用系统参数", path: "/systemConfig", icon: Setting },
  { title: "操作日志", description: "审查后台操作记录和行为轨迹", path: "/journalManage", icon: Document },
  { title: "我的消息", description: "查看系统通知与个人消息", path: "/myMessage", icon: Message },
];
</script>

<style scoped>
.hub-home {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
  color: var(--el-text-color-primary);
}
.hub-header { margin-bottom: 24px; }
.hub-eyebrow {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.12em;
  color: var(--el-color-primary);
}
.hub-header h1 { margin: 0 0 8px; font-size: 28px; font-weight: 650; }
.hub-lead { margin: 0; line-height: 1.7; color: var(--el-text-color-secondary); }
.hub-notice { margin-bottom: 32px; }
.hub-home h2 { margin: 0 0 16px; font-size: 18px; }
.hub-grid { row-gap: 16px; }
.hub-link { text-decoration: none; display: block; height: 100%; }
.hub-card { height: 100%; border-radius: 12px; }
.hub-card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: var(--el-color-primary);
}
.hub-card h3 { margin: 18px 0 8px; font-size: 16px; color: var(--el-text-color-primary); }
.hub-card p { margin: 0; line-height: 1.65; color: var(--el-text-color-secondary); font-size: 13px; }
.hub-link:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 4px; border-radius: 12px; }
.hub-footnote { margin-top: 24px; color: var(--el-text-color-placeholder); font-size: 12px; }
@media (max-width: 767px) {
  .hub-home { padding: 12px; }
  .hub-header h1 { font-size: 24px; }
}
</style>
