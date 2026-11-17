# Enterprise Agent Hub（企业级 AI Agent 业务执行与治理平台）

**[简体中文](README.zh-CN.md) | [English](README.md)**

> 使用 AI Agent 驱动既有 ERP、OA、CRM 等业务系统，在企业权限和业务规则约束下完成可审计、可恢复的业务操作。

**当前状态：V1.0 产品与架构设计阶段，尚未实现完整运行产品。**

## 项目愿景

企业已经有 ERP、OA、CRM 等系统；本项目不是重做 ERP，也不是普通的 AI 聊天机器人，而是在企业业务系统之上建设一层可复用的 **Agent 执行与治理平台**。

**架构原则：Agent 负责理解任务、查询和提出计划；确定性业务服务负责授权、审批、校验与最终写入。** 大模型输出不构成安全授权。

### 典型场景

用户提出：“查询逾期超过 30 天的应收账款，按责任人创建催收任务，单笔金额超过 10 万元的操作需要主管审批。”

系统应完成：

1. 用户认证、业务数据范围校验
2. Agent 调用已授权的 ERP 查询工具
3. 生成结构化、可审查的操作计划
4. 权限及风险策略校验
5. 高风险操作进入人工审批
6. 审批通过后复核业务数据并通过工具网关执行
7. 幂等写入催收任务并记录审计结果
8. 通过 WebSocket 向用户实时推送执行状态；异常可恢复或核对

## 总体架构

![Enterprise Agent Hub 系统架构](docs/architecture/architecture.svg)

```mermaid
flowchart TB
  USER[Vue 3 管理控制台] -->|HTTP REST| API[Django REST Framework]
  USER <-->|WebSocket| WS[Django Channels / ASGI]
  API --> ORCH[Task Orchestrator]
  ORCH --> CELERY[Celery Worker]
  CELERY --> AGENT[Agent Runtime / OpenAI Agents SDK]
  AGENT --> PLAN[结构化业务执行计划]
  PLAN --> POLICY[Policy Engine / RBAC / 数据范围]
  POLICY --> APPROVAL{需要人工审批?}
  APPROVAL -->|需要| HUMAN[审批决策与重新校验]
  HUMAN --> GATEWAY[Business Tool Gateway]
  APPROVAL -->|不需要| GATEWAY
  GATEWAY --> ERP[ERP Connector]
  GATEWAY --> OA[OA Connector]
  GATEWAY --> CRM[CRM Connector]
  ORCH <--> PG[(PostgreSQL)]
  CELERY -->|进度事件| LAYER[Redis Channel Layer]
  LAYER --> WS
  GATEWAY --> AUDIT[审计与业务执行记录]
```

**通信与执行分工：** DRF 提供任务创建、查询、审批等 REST API；Django Channels 负责 WebSocket 连接和实时事件；Celery 负责长时间运行的 Agent 任务与重试；PostgreSQL 保存权威状态；Redis Channel Layer 负责临时跨进程消息分发，不承担持久化。

## 技术栈

| 方向 | 技术 |
| --- | --- |
| 前端 | Vue 3、TypeScript、Vite、Pinia、Element Plus |
| 后端 API | Python、Django、Django REST Framework |
| 实时通信 | Django Channels、ASGI、WebSocket、channels_redis |
| Agent 执行 | OpenAI Agents SDK（通过适配层隔离） |
| 后台任务 | Celery、Redis |
| 数据库 | PostgreSQL、Django ORM、Django migrations |
| 追踪与评测 | OpenTelemetry、pytest、pytest-django、Agent Evaluation |
| 部署 | Docker Compose、ASGI Server（Daphne） |

## 核心模块

- **Agent Runtime Adapter**：模型与 Tool 调用、结构化计划输出
- **Task Orchestrator**：持久任务状态机、暂停、恢复、重试
- **Business Tool Gateway**：工具白名单、Schema 校验、业务授权、幂等执行
- **Governance Engine**：RBAC、组织数据范围、风险策略、审批
- **Business Connectors**：首先提供模拟 ERP；后续支持 OA、CRM 等
- **Realtime Communication**：Channels + Redis 实时推送任务进度、Agent 增量输出和审批通知
- **Observability & Evaluation**：Tracing、审计事件、工程测试和效果评测

## 文档导航

- [产品说明书（PRD V1.0）](docs/product/PRD-V1.md)
- [总体技术架构](docs/architecture/overview.md)
- [Django Channels 实时通信设计](docs/architecture/realtime-communication.md)
- [开发路线图](ROADMAP.md)
- [SVG 架构图](docs/architecture/architecture.svg)

## V1 开发范围

第一阶段重点完成**自然语言任务 → 结构化执行计划 → 受控工具调用 → 人工审批 → ERP 业务写入 → 实时反馈**的一条闭环。

V1 **不包含**：完整 ERP、拖拽式流程设计器、通用 SaaS 多租户、无限制 Agent 自主写入、复杂多 Agent 系统以及 Kubernetes 微服务集群。

## 开源说明

仓库目前是设计基线；演示场景使用虚构数据。实际代码、部署脚本和测试将按 [ROADMAP](ROADMAP.md) 逐步提交。开源许可证将在依赖及知识产权核查后确定，欢迎通过 Issues 提出改进建议。
