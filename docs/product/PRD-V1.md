# Enterprise Agent Hub — 产品说明书 V1.0

**定位：** 企业级 AI Agent 业务执行与治理平台  
**状态：** 产品与架构设计基线；不是已完成的产品  
**交付：** 开源、自托管、模块化单体；先实现模拟 ERP 场景

## 1. 产品定义

在现有 ERP、OA、CRM 之上构建通用 Agent 执行层。通过自然语言提交业务目标，由 AI 理解任务、查询受授权数据、形成结构化执行计划；由受控编排、权限策略、审批和业务工具网关进行实际写入和审计。

不重复建设完整 ERP；不提供无限制自主操作权。核心价值为**可靠、安全、可恢复的企业业务执行**。

## 2. 用户角色

| 角色 | 需求 |
| --- | --- |
| 业务用户 | 通过自然语言提出任务、查看处理结果 |
| 审批人 | 审核高风险业务操作 |
| 企业 IT 管理员 | 配置连接器、身份权限、策略与部署 |
| AI 工程师 | 扩展 Agent、工具、评测与可观测体系 |
| 审计员 | 检查操作轨迹与授权依据 |

## 3. V1 业务场景

指令示例：“查询逾期超过 30 天的客户，分析风险并创建催收任务，单笔超过 10 万元必须经主管审批。”

系统应完成：

1. 认证与数据范围校验
2. 通过只读 ERP Tool 查询客户及应收
3. Agent 生成**结构化、可审查**的操作计划
4. 独立策略引擎检查金额、人员与业务状态
5. 超额操作进入人工审批；其他合法操作按策略执行
6. Tool Gateway 调用 ERP 创建催收任务
7. 记录任务、审计、Trace 与结果
8. 对网络超时等不确定外部执行结果进行对账核实

## 4. 功能需求

| 编号 | 模块 | 最小交付 |
| --- | --- | --- |
| FR01 | Agent Runtime Adapter | Tool 调用、结构化输出、SDK 适配 |
| FR02 | Task Orchestrator | 任务和步骤、合法状态、持久化与恢复 |
| FR03 | Business Tool Gateway | 工具注册、参数 Schema、幂等、审计 |
| FR04 | Governance Engine | RBAC、组织数据范围、金额阈值 |
| FR05 | Human Approval | 审批、拒绝、超时、计划版本约束 |
| FR06 | ERP Connector | 模拟 ERP 应收查询和催收写入 |
| FR07 | Console | 任务详情、审批、执行轨迹 |
| FR08 | Observability | Trace、成本、错误、评测和审计 |
| FR09 | Deployment | Docker Compose、本地样例数据、CI |

## 5. 关键执行约束

- LLM、Prompt、普通 Guardrail 不是最终安全边界
- 所有外部业务写操作必须通过独立执行网关
- 审批绑定用户、业务对象、计划版本和操作范围；执行前二次校验
- 幂等以业务操作 ID 和可信上下文为依据，而非仅靠自然语言
- 外部写入超时若结果未知，进入核对状态，避免盲目重试
- 真实业务规则和数据正确性由 ERP / 业务 API 最终保证

## 6. 核心任务状态

`CREATED, PLANNING, VALIDATING, READY, WAITING_APPROVAL, EXECUTING, RETRYING, SUCCEEDED, REJECTED, FAILED, CANCELLED, NEEDS_RECONCILIATION`

## 7. 数据实体

- 身份与配置：`users`, `roles`, `agents`, `tool_definitions`
- 执行状态：`tasks`, `task_plans`, `task_steps`, `tool_executions`
- 治理：`policy_rules`, `approval_requests`, `audit_events`
- 投递与恢复：`business_outbox`
- 演示业务：`demo_receivables`, `demo_collection_tasks`

重要字段：`plan_version`、`operation_id`、`idempotency_key`、`request_actor`、`business_record_version`、`trace_id`。

## 8. API 草案

```http
POST   /api/v1/tasks
GET    /api/v1/tasks/{id}
GET    /api/v1/tasks/{id}/steps
POST   /api/v1/tasks/{id}/cancel
GET    /api/v1/approvals
POST   /api/v1/approvals/{id}/approve
POST   /api/v1/approvals/{id}/reject
GET    /api/v1/tools
GET    /api/v1/audit-events
```

在开发前补齐认证、数据范围、请求和响应 Schema、错误码、并发控制与重试语义。

## 9. 技术建议

| 层 | 技术 |
| --- | --- |
| 前端 | React / TypeScript / Ant Design |
| API | Python / FastAPI |
| Agent | OpenAI Agents SDK |
| 数据持久化 | PostgreSQL / SQLAlchemy / Alembic |
| 缓存与后台任务 | Redis / Worker |
| 追踪 | OpenTelemetry |
| 质量保障 | pytest、业务回归、Agent 评测 |
| 部署 | Docker Compose |

## 10. V1 不做

完整 ERP、通用 SaaS 多租户、可视化拖拽工作流、通用知识库产品、复杂多 Agent 协同、数十个连接器以及 Kubernetes 微服务平台。

## 11. 验收与质量指标

- 正常业务查询和催收任务创建可端到端复现
- 业务用户不可读取或修改超出数据范围的记录
- 超过阈值的写入在审批前不能执行
- 审批超时、拒绝或计划变更后不能继续原计划
- 同一业务操作重试不会产生重复任务
- 疑似执行成功的网络超时须先核对再补偿
- 服务重启可恢复中断任务
- 执行过程关联审计事件与 Trace
- 目标 40+ 工程测试、30–50 条评测样例（待实现并实测）

## 12. 求职展示重点

**数字化负责人：** 业务价值、系统集成、组织权限、流程治理、运维交付。  
**AI 架构师：** Agent Runtime、工具安全、结构化计划、可靠编排、异常恢复、Tracing 与 Evaluation。

## 13. 迭代计划

参见 [ROADMAP.md](../../ROADMAP.md)。

本文件为仓库内 GitHub 易读版产品概要；完整排版 Word 文件需在取得二进制上传权限后另行提交。
