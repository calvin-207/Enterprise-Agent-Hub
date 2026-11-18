# P2-B · Agent 会话、上下文与 SSE 执行事件流

> 交付日期：2026-11-18。P2-B 建立**可持久化的私有会话**及**RunEvent 的 SSE 状态事件流**。这不是模型 Token 流式生成：当前不会把 LLM 每个文字增量实时推送给浏览器。

## 1. 模块与持久化

- `agent_runtime.AgentSession`：唯一 UUID、Agent、所属用户、标题、是否归档、创建及更新时间；会话仅归本人所有，不开放管理员跨用户浏览。
- `agent_runtime.AgentMessage`：会话、AgentRun、角色（user/assistant）、内容、顺序 ID；每个 Run 至多一条 user 和一条 assistant 消息，由数据库唯一约束保护。
- `AgentRun.session`：可选 FK。原有无会话 `POST /runs/` 不变；新会话通过 `POST /sessions/{id}/runs/` 提交。
- `0003_sessions.py`：新增会话/消息表及可空关联，不删除旧任务。

创建 Run 时与 Outbox、初始 RunEvent、用户 Message 在**同一数据库事务**写入；幂等重放不重复追加消息。事务内锁定会话防止双发与并行追问；同一会话至多一个活动 Run。成功终态在同一事务落 assistant Message，失败/取消保留用户消息供审计但**不把失败消息加入模型上下文**。

上下文：执行时从同一会话最近最多 12 条**已成功完成的历史消息**构建 role/content 列表，并对单条消息限制 4000 字符；附加本次用户输入后交给 SDK Adapter。Mock Adapter 提供确定性的上下文承接演示，真实 SDK 适配器将历史 turns 传入 Runner。没有长期向量记忆或跨会话共享记忆。

## 2. API

统一前缀 `/api/platform/v1/`，使用原有 JWT 鉴权：

| 方法 | 路由 | 功能 |
| --- | --- | --- |
| GET / POST | `sessions/` | 仅当前用户的未归档会话列表 / 创建会话 |
| GET / PATCH | `sessions/{uuid}/` | 获取会话、活动 Run ID；修改标题或不可逆归档 |
| GET | `sessions/{uuid}/messages/?after=0&limit=50` | 按递增消息 ID 查询，最多 100 条 |
| POST | `sessions/{uuid}/runs/` | 提交新会话轮次，必须附 `Idempotency-Key` |
| GET | `runs/{uuid}/stream/?after=0` | 鉴权后按序输出 SSE RunEvent（支持 Last-Event-ID） |
| GET | `runs/{uuid}/events/?after=0` | 原有 REST 事件补查 |
| GET | `runs/{uuid}/` | 原有权威运行状态查询 |

新增会话示例：

```json
{"agent_id":"<已发布 Agent UUID>","title":"月度销售分析"}
```

提交新轮次：

```http
POST /api/platform/v1/sessions/{session_uuid}/runs/
Authorization: JWT <access_token>
Idempotency-Key: <每轮唯一 UUID>
Content-Type: application/json

{"message":"分析 9 月销售额"}
```

新请求 HTTP 202，幂等重放 HTTP 200；同会话已有活动 Run HTTP 409 `SESSION_BUSY`。会话拥有者可重新加载消息列表。归档仅允许无活动任务的会话进行；归档后只读、不能恢复或者继续提交新轮次。

## 3. SSE 协议

`GET /runs/{uuid}/stream/` 先验证 Run 所有者，再返回 `text/event-stream`。**JWT 必须放在 Authorization 头；不要把 Token 放进 URL**。SSE 每条为：

```text
id: 3
event: run-event
data: {"sequence":3,"type":"run.step_completed","payload":{"step":2,"kind":"TOOL_READ"}}

```

支持 `Last-Event-ID` 或 `after` 重播。每次连接最多持续约 15 秒，事件游标保存在数据库；连接超时后客户端携带最新游标重连，任务进入 SUCCEEDED/FAILED/CANCELLED 后发出 `stream-end`。

前端使用 `fetch` + ReadableStream 发送 JWT，而非原生不支持自定义 Authorization Header 的 `EventSource`；SSE 不可用时回退到 REST `events/?after=`，最终通过 Run 详情确认完成并从会话消息 API 重新获取答案。**SSE 只是低延迟通知，数据库查询才是最终权威。**

提示：当前 Django 的同步流式响应使用短时轮询数据库实现，适合低并发验收；面向高并发生产环境应升级为 ASGI 异步 SSE 或 Channels 消息唤醒、增加反向代理连接/缓存参数、监控长连接占用。

## 4. 页面

运行 `python manage.py migrate` 和 `python manage.py init`，后台新增 **Agent 会话** 菜单（`/agentChat`）。

页面支持：

- 选择用户已有运行授权的已发布 Agent、创建/切换会话、修改标题、归档
- 发送新消息、显示用户/Agent 历史消息
- 查看执行状态与近期 RunEvent、运行中请求取消
- 页面刷新后通过 Session.active_run_id 找到进行中的 Run 并恢复订阅
- 断线后通过 SSE ID 和 REST 回补，不要求用户重新提交任务

## 5. 权限与安全

- 会话和消息只允许所有者访问；即使平台超级管理员也不能通过 Session API 或关联 Run/Stream API 获取其他人的私有会话内容。
- 会话创建要求 Agent 已发布且当前用户具有运行授权；后续每轮发送再次检查授权。
- 会话内容为用户输入，可能包含隐私数据；当前以明文存于应用数据库供上下文复用。生产使用前必须完善敏感内容脱敏、数据保留周期、删除/导出策略、访问审计及消息级加密设计。
- Agent 回答记录限长、上下文轮数限制；此阶段不执行任意 SQL、Shell 或写工具。

## 6. 验收

```bash
cd backend
python manage.py check --settings=test_settings
python manage.py makemigrations --check --dry-run --settings=test_settings
pytest -q tests/test_agent_sessions_p2b.py tests/test_agent_runtime.py tests/test_agent_runtime_p1c.py tests/test_agent_runtime_p2a.py

cd ../frontend
npm test
npm run build
```

验收重点：会话归属隔离、管理员不能越权读取聊天内容、幂等不重复发消息、同会话拒绝并行、成功落助手回复、失败不污染上下文、消息游标查询、SSE 越权 404/未登录 401、Last-Event-ID 无丢失重放、前端生产构建。

**P2-B 后续工作**：生产高并发推送基础设施、真正的模型增量 Token streaming、完善持久对话上下文裁剪/Token 预算、可删除及合规处理历史消息，并结合真实付费模型进行流式请求与费用对账。
