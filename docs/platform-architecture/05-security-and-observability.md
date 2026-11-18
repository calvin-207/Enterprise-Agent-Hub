# 05 · 安全治理、密钥隔离、Tracing 与审计

## 1. 安全主体与客体

使用现有 `system.Users` / `Role` / `Dept` 做身份与组织基础，但平台**不能仅凭用户可见菜单就授权模型工具调用**。

每次 Tool 调用需要四项共同满足（AND）：

1. 当前 `actor` 真实认证且账号有效、具备操作客体权限；
2. 当前发布 `AgentVersion` 经 ToolGrant 明确允许该 Tool；
3. ToolDefinition 处于启用状态，Schema 和操作范围合法；
4. 当前 Policy 对 actor + Agent + Tool + 业务对象 + 动作 + 时间 + 风险判定为 ALLOW 或明确 WAITING_APPROVAL。

默认 DENY。任何权限缓存失效时必须重新查询权威数据库；绝不能因“查询异常”降级为允许。后台 API 管理权限与 Agent 可使用业务工具权限分离。

## 2. 工具类别的允许边界

| 工具类型 | P1 | P2/P3 条件 |
| --- | --- | --- |
| Mock 经营数据只读 | 允许（合成数据） | 同样经过校验/记录 |
| HTTP 外部 API 只读 | P2 | 域名/路径白名单、超时、重定向校验、TLS、出网策略、凭据隔离 |
| 数据库只读 | P2 | 专用只读凭据、固定查询模板/视图、参数绑定、行数/耗时限额、业务行级权限，不允许模型构造任意 SQL |
| HTTP/ERP 写操作 | P3 | ToolGrant、Policy、审批（按风险）、唯一 operation_id、审计、远端对账 |
| MCP 工具 | P3+ | 服务端信任分级、工具签名/能力审查、每次调用权限、隔离工具响应 |
| 任意 Python、shell、文件系统执行 | V1 排除 | 不允许作为通用低信任 Tool 开放 |

**SSRF 防护**：对 URL Tool 校验完整规范化 URL、域名和解析后 IP，拒绝 loopback/内网/链路本地/元数据地址；重定向后重新验证；配置独立网络 egress allowlist，不能仅靠字符串匹配域名。来自工具输出/网页的指令属于非可信数据，不得覆盖系统指令和 ToolGrant。

## 3. 凭据与模型配置

- 模型与 ERP 凭据只保存 `secret_ref`，运行时从 Secret Store/环境注入；数据库/前端不返回真实 key，不将 token 放进 Celery payload 或 Trace。
- 统一 ProviderAdapter（支持不同模型供应商），指定 base URL 与模型由管理员配置且经过 URL/host 安全检查。模型切换只影响配置版本，不影响 SDK 外部协议或 Tool 网关。
- Agent 发布前检验模型是否可用、工具授权是否有效、预算/超时/并发上限是否合法。
- API/LLM/工具输入输出限制大小，超大文件通过受控对象存储，URL 与 object key 授权及短期签名。
- 生产禁用 Django DEBUG 与公开 Schema，限制 CORS/CSRF、Cookie/WS Origin、JWT 过期和刷新；关键服务隔离账户、数据库权限和 Redis ACL。
- 统一错误响应：401/403/404/409/429/5xx 必须保持 HTTP 语义，不能只在 body 里填 400 而 HTTP 200。
- 创建审批决定必须再次确认**审批人本人权限**、被审批对象和当前业务版本；自己发起并自审属于默认禁止的高风险策略（可按业务定义例外，但需审计）。

## 4. 关键治理规则（P3）

```text
evaluate(
  actor_id,
  agent_version_id,
  tool_definition_id,
  operation_type,
  normalized_business_object,
  business_object_version,
  requested_scope,
  policy_version,
) -> DENY | ALLOW | REQUIRE_APPROVAL
```

审批项保存的 operation digest 包含：`actor`、`agent_version`、`tool_code`、参数摘要、业务对象 ID/版本、`policy_version`、`expires_at`、金额/风险阈值（若适用）。审批有效期和结果可复查；审批后写操作前重新读取业务数据，参数/版本变更则重新审批。

## 5. 可观测性三个层次

| 层级 | 记录内容 | 用途 |
| --- | --- | --- |
| RunEvent（持久） | 状态变化、Step ID、seq、事件类型 | 客户端 REST 补查、WS 投递 |
| Trace/Span（诊断） | run_id、step_id、模型/工具名称、耗时、错误类别、request_id | 运维定位、性能调优 |
| AuditEvent（治理） | 谁、何时、在什么资源上、经什么授权、执行了什么受控动作、结果 | 合规追溯，不可被普通后台编辑 |

数据默认不暴露完整 Prompt/工具返回；按策略脱敏、最小化、限时保存，审计不能用普通 `OperationLog` 代替。审计操作追加写，修改/删除仅通过独立、受控的保留策略。

**核心指标**（后续实现）：Run 成功率、P95 总耗时、Tool 错误率、模型响应/Token 数、平均单次成本、Worker 租约超期数、Outbox 待派发数、审批等待时长、未知远端结果数、每类 Agent 的政策拒绝率。

## 6. 数据范围与日志安全

- 读 Tool 查询 ERP 数据时以“用户真实数据范围 ∩ Agent ToolGrant 范围 ∩ 连接器许可范围”为最大权限，必须由服务器构造过滤条件；不能允许 LLM 生成任意部门 ID 访问数据。
- 针对跨部门、离职、角色权限撤销，运行中应在下一次 Tool 调用重新鉴权，允许安全停止 Run。
- 区分 `actor_user`（真实发起者）、`service_identity`（执行身份）与 `approved_by`（审批人）；不能用超级管理员 Worker 身份代替业务权限。
- Audit/Trace/异常日志不写 Redis 明文凭据、API Key、JWT、客户身份证/手机号等敏感字段；加密字段和对象存储应支持按生命周期清理。

## 7. 安全测试门槛

- 跨用户读取 Run、越权订阅 WS、伪造 ToolGrant、过期审批、参数替换、工具输出 Prompt Injection、SSRF（含跳转/DNS 变化）、模型诱导执行未授权工具、凭据意外出现在日志、重复请求/任务重放，均需负向测试。
- 超额调用、会话输入爆炸、无限工具循环、超大响应、循环重试应受到预算、超时和并发限制。
- P1 仅放行合成数据只读工具；未经审批或未验证业务写入幂等时不得进入生产。
