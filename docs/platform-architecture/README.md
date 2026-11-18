# Enterprise-Agent-Hub 平台层架构设计 V1

> 状态：**设计基线（Proposed）** · 日期：2026-11-18 · 对象：Enterprise-Agent-Hub · 目标：为后续 Codex 开发建立稳定契约。
>
> 本目录是平台设计，不表示 Agent Runtime、Tool Gateway 或审批功能已经实现。以代码、迁移、自动化测试和运行验收决定实际完成状态。

## 设计目标

将 Enterprise-Agent-Hub 定位为**企业级 Agent 运行、工具访问、任务自动化与治理平台**，而不是 ERP、智能问数或自动报表产品。业务应用以受控 Tool/Connector 与 Agent 配置形式接入，不侵入平台核心。

第一条通用闭环：

```text
管理端创建并发布 AgentVersion
  -> 绑定 ModelProfile 与 ToolGrant
  -> 用户启动 Session / Run
  -> API 认证授权、事务中持久化 Run 和 DispatchOutbox
  -> Dispatcher/Celery 消费
  -> Runtime 读取不可变配置快照
  -> Model Gateway -> Tool Gateway（每次调用重新鉴权）
  -> ExecutionStep + Event/Trace + TokenUsage
  -> Run 终态 -> WebSocket 通知 / REST 查询
```

第一条业务验收采用**模拟企业经营数据只读分析**；写操作及审批在第二增量引入。**ERP 同步、自动报表、企业微信等均是后续应用插件，不作为平台 V1 的硬依赖**。

## 文档导航

1. [01 总体架构与模块边界](01-overview-and-boundaries.md)
2. [02 数据库领域模型](02-domain-data-model.md)
3. [03 API 与事件契约](03-api-and-events.md)
4. [04 执行状态机与可靠性](04-runtime-state-and-reliability.md)
5. [05 安全治理与可观测性](05-security-and-observability.md)
6. [06 Codex 开发任务与验收](06-codex-delivery-plan.md)
7. [07 架构决策记录](07-decisions-and-risks.md)

## 已实现 / 待实现边界（按 2026-11-18 仓库核对）

| 范围 | 仓库实际情况 | 平台层后续动作 |
| --- | --- | --- |
| Django 5.2 / DRF / Vue 3 / Element Plus | 已有应用代码 | 复用；保持现有菜单和权限兼容 |
| User/Role/Dept/Menu | 已有模型和权限中间件 | 新增 Agent/Tool 对象级授权，不把菜单权限当工具权限 |
| Celery 5.6 / Redis Worker | 已接通并有测试 | 复用任务基础，不把 Redis 当状态真相 |
| django-celery-beat / TaskDefinition / TaskSchedule | 已有 Cron API 与前端 | 增加 Agent 类型前先设计可信适配器 |
| automation.TaskExecution | 记录检测任务的 queued/running/success/failed | **保留原表**；AgentRun 单独建模，可关联原任务记录 |
| OpenAI Agents SDK / Agent 数据表 | 尚未接入 requirements 或建模 | 在 P1 建立可替换 SDK Adapter |
| Agent Tool Gateway / Approval / Trace | 尚未实现 | 按本设计逐期开发 |
| PostgreSQL | 项目支持配置，CI 主要使用 SQLite | V1 建立生产数据库集成测试和迁移验证 |
| Django USE_TZ | 当前为 False、TIME_ZONE Asia/Shanghai | 时间存储统一 UTC 的迁移必须显式规划，不得静默变更 |

## 非目标

- V1 不做多租户 SaaS、不内置完整 ERP、不做用户自定义任意 Python/SQL 代码执行。
- 不在第一阶段做拖拽 Workflow、多 Agent 协同和高可用分布式调度器。
- 不为了“微服务化”拆分 Django API、模型存储与事务边界。
- 不把 LLM 输出、Prompt 或模型 Guardrail 视为授权依据。

## 进入实施阶段的门槛

- 本目录所有跨模块契约、状态机和不变量已有 CI 测试清单。
- P0 只提交文档、ADR 和必要验证脚本；**不创建尚未使用的 Django App、迁移、菜单**。
- 各阶段均须保持现有 Automation V2 和登录权限兼容；失败可以回滚至上一迁移及版本。
