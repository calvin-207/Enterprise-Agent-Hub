# 03 · API、运行契约与事件协议

> **Proposed，不是当前线上接口。** 原有 `/api/automation/`、`/api/system/` 保持兼容。新平台 API 统一 `/api/platform/v1/` 前缀；所有业务资源严格检查 JWT、主体权限与对象数据范围，错误必须保留正确 HTTP 状态码。

## 1. 核心 SDK 无关接口

```python
from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True)
class ActorContext:
    user_id: int
    organization_scope: tuple[str, ...]
    request_id: str
    permissions_version: str

@dataclass(frozen=True)
class StartRunCommand:
    agent_id: str
    version_id: str | None
    session_id: str | None
    input: dict
    idempotency_key: str
    deadline_seconds: int | None = None

class AgentRuntimeService(Protocol):
    def start(self, command: StartRunCommand, actor: ActorContext) -> dict: ...
    def get(self, run_id: str, actor: ActorContext) -> dict: ...
    def cancel(self, run_id: str, actor: ActorContext, reason: str) -> dict: ...

class ToolGateway(Protocol):
    def invoke(self, tool_code: str, arguments: dict, context: dict) -> dict: ...
```

此处是接口草案，实际实现建议以 Django Service + Pydantic/DRF Serializer 验证输入；`ActorContext` 由服务器生成而非接受客户端自报 user_id。运行结果返回权威状态，不能把 Celery AsyncResult 当对外 REST 模型。

## 2. REST 路由契约

| 资源 | 路由 | 行为 |
| --- | --- | --- |
| Agent | GET/POST `/agents/` | 分页列表、创建草稿 |
| Agent 详情 | GET/PATCH `/agents/{id}/` | 读取/修改元数据 |
| Agent 版本 | GET/POST `/agents/{id}/versions/` | 新建不可变版本候选 |
| 发布版本 | POST `/agents/{id}/versions/{version_id}/publish/` | 发布前校验模型与工具授权 |
| 模型配置 | GET `/model-profiles/` | 返回可用配置，不返回密钥 |
| 工具目录 | GET `/tools/` | 返回已授权且已启用工具及 Schema |
| 会话 | POST/GET `/sessions/`，GET `/sessions/{id}/` | 会话创建/查询 |
| Run | POST `/runs/` | 幂等创建 Run，202 |
| Run | GET `/runs/{id}/` | 当前权威状态、结果概要 |
| Run 步骤 | GET `/runs/{id}/steps/` | 可分页追踪步骤 |
| Run 事件 | GET `/runs/{id}/events/?after=123&limit=100` | WS 重连补查 |
| 取消 Run | POST `/runs/{id}/cancel/` | 请求取消，可能尚需工具步骤完成 |
| 审批 | GET `/approvals/`; POST `/approvals/{id}/decisions/` | P3；绑定操作摘要和版本 |
| 运行指标 | GET `/runs/{id}/usage/` | P2；Token 与成本 |
| 审计查询 | GET `/audit-events/` | P3；只读受限 |

首期 P1 只实现 Agent/Version/Tool Catalog/Run/Steps/Events，Session/模型成本/审批按计划扩展，不做伪实现。

### 创建 Run

```http
POST /api/platform/v1/runs/
Authorization: Bearer <JWT>
Idempotency-Key: 5b983621-d0db-44c5-9174-743e4bb4c954
Content-Type: application/json
```

```json
{
  "agent_id": "0c0653b9-0000-4000-9000-f92b96ba0123",
  "session_id": null,
  "input": {"message": "分析本月销售变化"},
  "deadline_seconds": 120
}
```

`user_id`、`role_ids`、`tool_grants`、`model_api_key` 不允许由请求指定；它们由后端安全上下文查出。

**202 Accepted（已排队，示例）**：

```json
{
  "id": "7f4fdb20-8e72-4b6b-a069-cd91107ba857",
  "status": "QUEUED",
  "status_version": 1,
  "agent_version_id": "07bcfd9f-87ab-4973-8fd0-cc7e8e43a0fd",
  "submitted_at": "2026-11-18T01:00:00Z",
  "links": {
    "self": "/api/platform/v1/runs/7f4fdb20-8e72-4b6b-a069-cd91107ba857/",
    "events": "/api/platform/v1/runs/7f4fdb20-8e72-4b6b-a069-cd91107ba857/events/"
  }
}
```

缺少 Idempotency-Key 返回 400；同用户同 key 同 payload 返回已有 Run（状态码 200 或 202，需实现时统一）；同 key 不同 payload 返回 409。后台权限禁止时返回 403，未登录返回 401；未知/越权资源防枚举返回 404（具体由安全策略决定），频率/配额限制返回 429，运行预算不通过返回 422。

### Run 详情响应（示例）

```json
{
  "id": "7f4fdb20-8e72-4b6b-a069-cd91107ba857",
  "status": "SUCCEEDED",
  "status_version": 6,
  "step_count": 3,
  "result": {
    "summary": "本月销售较上月下降 8%，主要集中在渠道 A。",
    "evidence_refs": ["demo:aggregate:2026-11"]
  },
  "error": null,
  "created_at": "2026-11-18T01:00:00Z",
  "finished_at": "2026-11-18T01:00:22Z"
}
```

## 3. WebSocket 事件契约

WS 连接：`/ws/platform/v1/runs/{run_id}/`。推荐短期、授权范围限定的 WS 票据或 Django 安全的 JWT 认证中间件，不把长期 JWT 放在 URL query；连接时和每次订阅都验证 actor 可访问对应 Run。

服务端事件（示例）：

```json
{
  "event_id": "evt_7f4f_000012",
  "run_id": "7f4fdb20-8e72-4b6b-a069-cd91107ba857",
  "sequence": 12,
  "type": "run.step_completed",
  "timestamp": "2026-11-18T01:00:17Z",
  "payload": {"step_id": "step_0003", "status": "SUCCEEDED"}
}
```

事件类型：`run.queued`, `run.started`, `run.delta`（非持久逐 Token 可允许丢包）, `run.step_started`, `run.step_completed`, `run.waiting_approval`, `run.completed`, `run.failed`, `run.cancel_requested`。审计和状态事件必须持久化，逐 Token 文本可抽样/聚合并脱敏。

- 事件顺序以 `(run_id, sequence)` 为准，不以发送顺序为准。
- WS 是“尽力实时”，断线重连从 REST `events?after=...` 补齐；前端按 sequence 去重。
- 写数据库成功后才推送 WS（可通过 Outbox），绝不因为 WS 断开改变运行最终状态。
- 先有 REST 完整查询，再有 WS 优化体验，避免前端只能靠 socket 才看得到结果。

## 4. 错误对象规范

```json
{
  "error": {
    "code": "TOOL_PERMISSION_DENIED",
    "message": "该 Agent 未获准访问此工具",
    "request_id": "req_abc",
    "retryable": false,
    "details": {}
  }
}
```

基础错误码：`AUTH_REQUIRED`, `FORBIDDEN`, `RESOURCE_NOT_FOUND`, `INVALID_ARGUMENT`, `IDEMPOTENCY_CONFLICT`, `AGENT_VERSION_NOT_PUBLISHED`, `MODEL_UNAVAILABLE`, `TOOL_PERMISSION_DENIED`, `APPROVAL_REQUIRED`, `RUN_CANCELLED`, `RUN_DEADLINE_EXCEEDED`, `UPSTREAM_RESULT_UNKNOWN`。

不要直接返回第三方模型错误堆栈、真实凭据、业务敏感查询结果；将异常详情记录到受限日志，API 返回用户安全信息。保留标准 HTTP 4xx/5xx，不把鉴权错误包装为 HTTP 200。

## 5. 并发版本与速率约束

- `POST /runs/` 必须带 `Idempotency-Key`，并验证 payload hash；最大任务时长、输入大小、每日配额和并发数由服务端配置。
- `POST /.../publish/` 使用期望版本号或 If-Match 做 CAS，拒绝覆盖已发布版本。
- `cancel` 只表示请求停止，不假定已提交的第三方写操作可以撤销。
- API schema 使用 DRF Spectacular，所有端点有权限/响应/错误契约测试。
