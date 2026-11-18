# Roadmap / Enterprise Agent Hub 开发路线图

> 更新时间：2026-11-18。当前**已实现**基础系统（Django/DRF/Vue、用户角色菜单）与 Automation V2（Celery、Redis、django-celery-beat、自动化任务与 Cron 管理页面）；Agent Runtime P1-C 的 Mock 模型、只读 Tool Gateway 及执行追踪已实现；真实 OpenAI SDK Adapter 已接入但尚需真实密钥/模型联调。P2-A 已增加管理员模型配置、Token 费用估算、协作取消和入队限额。治理审批、业务写操作和 Workflow **尚未实现**。
>
> **架构基线**：[docs/platform-architecture/README.md](docs/platform-architecture/README.md)；**Codex 任务与验收**：[06-codex-delivery-plan.md](docs/platform-architecture/06-codex-delivery-plan.md)。

## 已完成基座（截至 2026-11-18）

- Django 5.2 / DRF、Vue 3 / Vite、已有用户、角色、部门、菜单管理
- Celery + Redis Worker 运行链路和 CI 联调
- 自动化任务执行记录、管理员页面与任务状态
- django-celery-beat 的数据库 Cron 计划、任务定义、启停、立即触发及 UI
- 现有 CI 的 pytest、Vitest、Vite 构建、Migration 检查

## 2026-11-18 P1-A 进展\n\n- 已新增 `agent_catalog`（Django 标签保留 agents）、`model_gateway`、`tool_gateway` 三个最小模块及迁移；`model_gateway` 和 `tool_gateway` **目前仅是配置目录，不包含真实模型/工具执行**。\n- 已新增 Agent 草稿、不可变发布版本、用户运行授权、工具授权撤销 API 和 Agent 管理前端页面。\n- 模拟目录由 `python manage.py bootstrap_mock_catalog` 显式创建；P1-C 已可通过 Mock 模式运行 Agent。\n- [P1-A 交付与首次使用说明](docs/platform-architecture/08-p1a-implementation.md)。\n\n## P1-B / P1-C 实施进度

- P1-B：AgentRun、RunStep、RunEvent、DispatchOutbox、可靠派发和状态机已提交。
- P1-C：已接入 OpenAI Agents SDK 适配器、离线 Mock Agent Loop、每次鉴权的只读 Tool Gateway、任务结果与执行轨迹，新增 Agent 执行前端页面。
- 完整说明：[P1-B](docs/platform-architecture/09-p1b-implementation.md) · [P1-C](docs/platform-architecture/10-p1c-runtime-implementation.md)。
- P2-A：Provider/ModelProfile 管理、环境变量密钥引用、ModelUsage Token/费用估算、用户配额、协作取消及前端页面已提交。详见 [P2-A 文档](docs/platform-architecture/11-p2a-model-governance.md)。\n- **尚未完成：** 实际付费模型联调与账单核对、完整运行成本预算/报警、会话、工作流、业务写操作审批与多步恢复。

## 平台优先建设顺序

| 阶段 | 实施内容 | 交付与验收 |
| --- | --- | --- |
| P0 · 平台架构契约 | 模块边界、状态机、API、领域模型、ADR、时间/数据库迁移策略 | 文档评审；旧功能 CI 无回归 |
| P1-A · Agent 定义 | Agent、不可变 AgentVersion、ToolGrant、模型/工具配置与资源权限 | 发布版本，不允许越权或修改已发布内容 |
| P1-B · Run 核心 | AgentRun、Step、Event、DispatchOutbox、幂等 Run API、Celery Dispatcher | 重复 POST 去重、Worker 竞争、Broker 失败可恢复 |
| P1-C · Runtime V1 | SDK Adapter、Mock 只读经营数据 Tool、Agent Loop、预算和超时 | 用户提交自然语言分析 → 真实工具调用 → 结果/步骤持久化 |
| P2 · 体验与观测 | Session/Message、Model Gateway、模型用量和成本、Channels 推送与补查 | 刷新/断线不丢状态，跨用户隔离 |
| P3 · 治理与审批 | Tool Gateway 可写操作、Policy、Approval、Outbox、远端对账、审计 | 越权拒绝、审批前禁写、重复操作不重复写 |
| P4 · 自动化接入与 Workflow | AgentRun 和现有 TaskSchedule 受控联动，顺序/条件/审批流程 | 手动/定时同一 Agent，执行状态与审计统一关联 |

## 第一条演示任务

`分析本月销售变化` → Agent 调用本地 Mock 只读经营数据工具 → 生成有来源的结论 → 保存 Run、Step、Event、用量 → 前端查询结果。

第二条演示才引入模拟 ERP 的应收查询与催收审批，用于证明平台对工具治理的复用能力，而非开发完整 ERP。

## 不做

- 通用多租户 SaaS、完整 ERP、任意 Python/Shell/SQL 代码执行、复杂拖拽 Workflow、第一版就做微服务和 Kubernetes。
- 未经过安全网关授权的自动业务写入、没有幂等/对账的高风险重试。

原始 12 周路线图中的“基础框架待建设”“Celery 待接入”已由实际代码实现，不再作为新的开发任务重复投入。后续每阶段均须附真实 CI 和演示验收记录。
