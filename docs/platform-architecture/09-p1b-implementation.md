# P1-B 实施说明 · AgentRun 与可靠派发

> 日期：2026-11-18。P1-B 建立 Agent 运行基础设施，不包含真实 LLM 推理或工具执行。Worker 收到任务后会安全落库为 `FAILED / RUNTIME_NOT_IMPLEMENTED`，这是明确的阶段边界，不表示 Agent 执行成功。

## 已新增

- `agent_runtime.AgentRun`：独立于 `automation.TaskExecution` 的运行真相，绑定已发布 AgentVersion、用户、规范化输入摘要、配置快照、幂等键、超时与租约。
- `RunStep` / `RunEvent`：按 Run 内递增的 sequence 记录步骤和可补查的状态事件。
- `DispatchOutbox`：与 AgentRun、初始事件在同一数据库事务内写入。Broker 不可用时保存待重发记录，避免 `on_commit(task.delay)` 丢单。
- `dispatch_agent_outbox` 管理命令：独立派发进程，发送 `agent_runtime.execute`，具备退避和过期租约补偿。可用 `--once` 进行验证。
- Worker：按数据库 CAS 从 QUEUED 抢占 RUNNING，只有持有原租约 token 才能修改终态。重复消息不会重复执行。
- API：幂等创建、运行列表、详情、步骤、事件游标。

## 首次部署

```bash
cd backend
python -m pip install -r requirements.txt
python manage.py migrate
# 确保 Redis、Django API 和 Celery Worker 正常启动
celery -A main worker --loglevel=info --concurrency=2
# 在独立进程中运行 Outbox 派发器；测试可加 --once
python manage.py dispatch_agent_outbox --interval 2
```

**Dispatcher 必须是独立于 API 和 Worker 的长期进程**；不能指望每次 HTTP 调用主动连接 Broker，也不能只运行 Celery Beat。当前无需再新增 Agent 菜单，P1-A 管理界面仍正常使用。

## API

统一 `/api/platform/v1/`：

| 方法 | URL | 功能 |
| --- | --- | --- |
| POST | `runs/` | 创建 Run；必须提供 `Idempotency-Key` 请求头 |
| GET | `runs/` | 当前用户的最近 100 条 Run（管理员可见全局） |
| GET | `runs/{uuid}/` | 查看权威状态 |
| GET | `runs/{uuid}/steps/` | 获取步骤（最多 500） |
| GET | `runs/{uuid}/events/?after=0&limit=100` | 事件游标补查 |

示例：

```http
POST /api/platform/v1/runs/
Authorization: JWT <token>
Idempotency-Key: 0d96b26a-5e35-43d4-9789-2d91bc24de0f
Content-Type: application/json

{"agent_id":"<已发布 Agent UUID>","input":{"message":"分析本月销售情况"},"deadline_seconds":120}
```

成功初次提交 HTTP 202，再次同键同内容 HTTP 200，不同内容 HTTP 409。未经授权不能创建或读取别人的 Run。Runtime 未实现时，最终状态为 FAILED + RUNTIME_NOT_IMPLEMENTED（不产生伪分析结论）。

## 可靠性与阶段限制

- DB 同事务写 Run、RunEvent 和 DispatchOutbox。Outbox Dispatcher 通过条件更新抢占派发记录，允许重复消息但不允许两个有效 Worker 同时 claim 同一 Run。
- Outbox 网络错误指数退避，`last_error` 不包含连接凭据。Sent 状态表示 Broker 派发已确认，不代表业务执行成功。
- Worker 租约超期，由 dispatcher 的循环检查标记 `FAILED / WORKER_LEASE_EXPIRED`；**P1-B 不尝试恢复/重放未知业务副作用**，P1-C 必须引入 Step Checkpoint 和操作级幂等再开放真正执行。
- 当前部署环境沿用 `USE_TZ=False` 与 Asia/Shanghai，不能直接把现存 naive 时间当 UTC。在生产新环境切换时区前必须执行架构 ADR 所要求的兼容迁移。
- 示例代码仅存输入 JSON。生产业务需增加 PII 脱敏、对象存储与保留期限，不要直接将个人敏感数据传到 P1-B API。
- 当前没有流式 Token、ToolGateway 实际调用、Approval、长任务恢复或自动取消远端写操作。
- 现有 Automation V2 不被修改；AgentRun 不使用旧 TaskExecution 四态替代。

## 验收

```bash
cd backend
python manage.py check --settings=test_settings
python manage.py makemigrations --check --dry-run --settings=test_settings
pytest -q tests/test_agent_runtime.py
```

测试覆盖：幂等、发布版本绑定、越权、撤权后重放拒绝、Outbox 失败重投、租约 CAS、防重复 Worker、最终状态及事件顺序。正式投产前需额外补 PostgreSQL 并发与 Redis 真实 Broker 压力测试。

**下一步 P1-C**：为 Worker 增加可替换 RuntimeAdapter、模型调用、只读 mock_sales_summary Tool、执行轮次/Token/时间预算及 Step Checkpoint；不改变上述 Run/Outbox 的公开契约。
