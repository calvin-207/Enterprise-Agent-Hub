# 07 · 架构决策记录与开放风险

## ADR-001：模块化单体 + 独立 Celery 进程

**状态：Accepted for V1 design。** 一个 Django 工程承载 ORM、API 与应用服务；API/Channels、Worker、Beat、Dispatcher 分进程部署。跨模块用服务契约组合，避免网络微服务调用和分布式事务提前复杂化。

**再评估触发**：不同模块需要独立发布、组织权限显著不同、CPU/模型 I/O 扩容冲突或单数据库成为瓶颈。

## ADR-002：AgentRun 与 automation.TaskExecution 分离

**状态：Accepted。** 原 Automation 四态服务通用计划任务，AgentRun 有审批、恢复、对账、取消和版本快照的丰富状态。通过可空 ID 映射整合 UI，不重命名原表，也不做 Proxy Model 伪复用。

**风险**：两套列表产生重复展示。通过统一“任务中心视图 / 聚合服务”解决，**不合并状态权威**。

## ADR-003：数据库权威 + Transactional Outbox

**状态：Accepted。** PostgreSQL 提供 Run/Step/Event/Outbox 唯一真相，Celery 是至少一次可重复投递，worker 层按 Run 及 Tool 操作键去重。WS/Redis 是通知而不是权威。

**风险**：Outbox Dispatcher 与租约 Reconciler 增加运维成本。P1 只实现最小定时扫描/告警，而不是引入新的大型消息队列。

## ADR-004：模型 SDK 以适配器封装

**状态：Accepted。** 首个 Adapter 选 OpenAI Agents SDK，但 AgentVersion、Run、Tool、Trace 的数据库 schema 不绑定 SDK 内部对象；后续其他 LLM/provider 走 ModelGateway，不要把 OpenAI API 格式作为领域模型。

**风险**：SDK 升级导致 Tool/Trace 结构变化。以集成测试及版本固定应对。

## ADR-005：默认拒绝写 Tool；按风险审批

**状态：Accepted。** P1 演示只读。P3 引入写 Tool 时，可信 Gateway 负责身份、AgentVersion ToolGrant、策略、审批摘要/过期/业务版本和操作幂等。Prompt、LLM Guardrail 与 UI 权限**不是**最终授权层。

## ADR-006：先数据库动态 Cron，后 Workflow

**状态：Accepted。** 复用已有 django-celery-beat；可信适配器把 Cron 转换为受控 AgentRun 创建命令。当前 Cron 仅允许 `ping` / `database_probe`，**不声明**已经支持 Agent 定时执行。

## ADR-007：时间规范与兼容迁移（待具体实施方案）

**状态：Decision required before P1 DB implementation。** 当前 Django `TIME_ZONE=Asia/Shanghai`、`USE_TZ=False`；新业务推荐 UTC aware。不能在生产中直接切换 `USE_TZ` 而不处理历史表、Beat 时区/last_run_at 和 API 格式。

实施前必须确定：新部署 vs 旧库迁移步骤、数据库时区、历史 naive 转换规则、灰度检查与回滚策略。未完成前，P1 不能同时混用本地 naive 和 UTC aware 时间。

## ADR-008：企业权限继承已有 RBAC，但工具权限独立

**状态：Accepted。** system.Users/Role/Dept 是身份来源；Agent 资源 ACL、ToolGrant、数据范围、治理策略由对应模块承载。菜单访问权限不自动赋予业务数据读取或写入能力。

## 关键待解风险（按优先级）

| 优先级 | 风险 | 应对 / 完成标准 |
| --- | --- | --- |
| P0 | 仓库 README/ROADMAP 当前仍写“未开始实现” | 文档修正，保持和现有代码同步 |
| P0 | 当前 `USE_TZ=False` 且计划已有 Asia/Shanghai 时间 | 确认 UTC migration 方案及时间回归测试 |
| P0 | PostgreSQL 锁/事务与 SQLite 测试差异 | CI 新增 PostgreSQL 的 Outbox/租约/并发用例 |
| P1 | Outbox 可靠派发缺失 | P1-B 添加 Dispatcher / 超时恢复及运维指标 |
| P1 | 现有 API 可能把权限错误封装 HTTP 200 | Agent API 明确 HTTP 401/403，测试防回归 |
| P1 | 前端现为 JavaScript，设计文档曾写 TypeScript | 分模块渐进引入 TS 或保持 JS，避免无关大重构 |
| P1 | Agent 版本快照可能保存密钥 | 快照只保存 secret_ref + 版本号，自动化检查敏感字段 |
| P2 | WS 断线/用户撤权泄漏数据 | 按 Run 订阅鉴权、游标补查、短期票据 |
| P3 | 外部 ERP 写超时结果未知 | OperationRecord + remote lookup + RECONCILING |
| P3 | Tool 输出间接提示注入、SSRF | 只读工具网关、安全出网策略和攻击测试 |
| P4 | Cron 与 AgentRun 双态展示 | 明确聚合查询，分别保留各自状态 |

## 设计变更流程

修改任一核心不变量、外部 API、状态名、模型间依赖或数据迁移策略，必须：

1. 追加 ADR/修改本目录对应文档；
2. 提供数据/接口兼容策略及回滚说明；
3. 修改契约/测试用例并在 CI 验证；
4. 明确对应阶段的 Definition of Done；
5. 不得只凭“架构图已画好”宣称功能已上线。
