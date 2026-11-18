# 06 · Codex 工程任务分解与验收标准

> 给 Codex 的实施契约。**每个阶段独立 PR、Migration 和测试，不允许在一个提交里一次性搭建所有空模块。** 开发时以本目录文档及现有仓库代码为准。项目是 Vue 3 + JS SFC、Django 5.2/DRF、Celery + Redis + django-celery-beat；不要假定已安装 OpenAI Agents SDK。

## 执行规则

1. 改动前检查 `git status`、当前主分支、已有迁移、`system.Users`、`automation.TaskExecution`，避免覆盖现有业务。
2. 建立小 PR，先写失败测试，再补服务和 API；数据库迁移必须提交。
3. 禁止修改/删除现有 Automation V2 记录结构以假装 AgentRun；如果需要关联，新增 nullable 关系字段/映射服务。
4. 业务逻辑放 service 层，视图只验证请求和授权，Worker 只消费 ID，Tool Gateway 管理工具调用权限。
5. 每批必须通过：`python manage.py check`、`python manage.py makemigrations --check --dry-run`、`pytest -q`、`npm test`、`npm run build`；P2 起增加 PostgreSQL/Redis 集成测试。
6. PR 说明列出接口、迁移、威胁、测试、回滚步骤和未交付边界。

## P0 · 架构基线与环境验证（不新增大规模业务代码）

**输出**：本目录文档/ADR、API Schema 草案、测试矩阵、用于开发的模拟企业经营数据协议。

**检查**：
- 确认 README/ROADMAP 不再声称“所有实现尚未开始”。
- `system` 和 `automation` 的历史测试及接口无回归。
- 明确 PostgreSQL 和时区迁移策略；任何 schema 变更必须有 Migration。
- 确认已知遗留安全项：生产 DEBUG/Schema、JWT/WS、工具执行不可直接继承菜单权限。

**验收**：文档评审通过、已有 CI 全绿、优先级清晰。

## P1-A · Agent 定义、版本与权限（第一开发 PR）

**模型**：`Agent`、`AgentVersion`、`AgentAccessGrant`、`ToolDefinition`、`ToolGrant`、`ModelProvider`、`ModelProfile`（最少可以先模型引用的轻量只读表）。

**API**：草稿创建/编辑、发布版本、目录查询；发布前验证是否已绑定模型与白名单工具。

**不可妥协的测试**：
- 未登录 401、普通无权限 403、越权资源 404/403；
- 未发布版本不能 Run；
- 发布后版本内容不可修改；
- 不允许客户端传工具 Python callable 或模型 API Key；
- 删除 ToolGrant 不会保留旧的新增权限（运行时重校验）。

**验收**：管理员可以创建一个“模拟销售分析 Agent”并发布，普通受权用户可查到可运行版本，不能直接执行外部业务代码。

## P1-B · Run 状态、Outbox 与 API（第二开发 PR）

**模型**：`AgentRun`、`RunStep`、`RunEvent`、`DispatchOutbox`。**不要**复用四态 `TaskExecution` 表替代 AgentRun。

**API**：`POST /runs/`、`GET /runs/{id}/`、`GET /runs/{id}/steps/`、`GET /runs/{id}/events/`。

**内部**：ActorContext、Idempotency-Key、状态转移 CAS、唯一约束、Outbox 事务内创建、Dispatcher/Celery Worker 消费 run_id、Run lease 释放。

**测试**：重复提交复用 Run，不同 body 409；Outbox 补偿；两个 Worker 竞争只运行一次；事件顺序不可回退；失败可查询且不泄露凭据。

**验收**：从 API 发起 Run，Worker 接收、写 Step/事件，前端（初期可 REST 轮询）可查询最终状态。

## P1-C · 单 Agent Runtime + 只读 Tool（第三开发 PR）

**实现**：
- 安装并锁定经兼容性验证的 OpenAI Agents SDK 版本；封装 `RuntimeAdapter`，隔离 SDK 对外契约；
- 一条本地 Mock 数据工具 `mock_sales_summary`，输入 Schema 有效，结果可引用来源；
- 限制模型轮次、Tool 调用次数、Token、执行秒数及并发；
- Tool Gateway 每次核对 Actor 权限与发布版本 ToolGrant；
- 按轮次保存 Model/Tool Step，输出最终有证据的分析文本。

**测试**：模型/工具使用 mock（CI 不调用真实付费 API）；越权、超时、坏 JSON、SDK 抛错、重复 Tool、预算耗尽、循环调用。

**验收演示**：用户创建任务“分析本月销售变化” → 发起 Run → 执行 `mock_sales_summary` → 记录 Step 和 Event → 展示分析结果 → 审计记录不可被客户端伪造。

## P2 · 会话、模型网关、成本与实时消息

**功能**：Session/Message、模型适配、密钥引用、TokenUsage、RunEvent REST 游标、Channels 事件推送、断线恢复。

**测试**：跨用户 Session 隔离；模型限额；Trace 脱敏；WS 重连/乱序去重；账号角色撤销后工具访问立即禁止。

**验收**：浏览器 Run 页面可以看到实时进度，并在刷新/断线后恢复到数据库最新状态。

## P3 · Governance + 写工具 + 审批

**功能**：Policy、ApprovalRequest、OperationRecord、签名/操作摘要、审批二次校验、业务幂等、未知远端结果对账。

**演示**：模拟 ERP 应收催收。单笔 >10 万元经授权审批；拒绝不写入；改动业务金额后旧审批失效。

**测试**：审批越权、超期、重放、Worker 重启、写工具超时/已成功、无权限读写、重复消息和远端幂等冲突。

**验收**：模拟写业务系统可以证明不会因为 Agent/Worker 重试创建两条相同催收任务。

## P4 · Automation 适配与可扩展工作流

**功能**：允许定义可信 `agent_run` 自动化任务类型；AgentRun 与 TaskExecution/TaskSchedule 关联；流程编排首先支持顺序/条件/人工审批三种节点。

**测试**：Cron 同分钟去重、Agent 版本变更/权限撤销、暂停计划、任务失败恢复、历史 Run 可复现。

**验收**：同一个 Agent 可手动执行，也可由已有 Cron 计划触发，统一查看 Run 状态。

## 开发验收矩阵

| Case | P1-A | P1-B | P1-C | P2 | P3 | P4 |
| --- | --- | --- | --- | --- | --- | --- |
| 身份、Agent/工具权限 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Agent 发布版本不可变 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Run 幂等、状态 CAS、Outbox | — | ✅ | ✅ | ✅ | ✅ | ✅ |
| 工具 Schema、模型轮次/预算 | — | — | ✅ | ✅ | ✅ | ✅ |
| Session/WS/成本/脱敏 | — | — | — | ✅ | ✅ | ✅ |
| 审批、业务写入对账 | — | — | — | — | ✅ | ✅ |
| Cron Agent 绑定 | — | — | — | — | — | ✅ |

## 推荐 Codex 开始指令

```text
工作仓库：calvin-207/Enterprise-Agent-Hub。
执行 docs/platform-architecture/06-codex-delivery-plan.md 的 P1-A，
严格遵守 README 和 01/02/03/05/07 设计文档。
保持现有 system、automation 模型/API、GitHub CI 兼容。
先创建最小模型、迁移、序列化、权限和 API 测试，然后提交一个 PR。
不要实现尚无验收的 Agent Runtime、写操作、复杂 Workflow。
回报：改动清单、迁移影响、权限边界、测试命令及通过情况、后续风险。
```
