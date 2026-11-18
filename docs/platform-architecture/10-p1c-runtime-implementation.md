# P1-C · Agent Runtime 与模型/工具执行实现

> 实现日期：2026-11-18。P1-C 在 P1-B 的可靠派发与 AgentRun 数据模型之上添加单 Agent Runtime。**Mock 模型可完全离线运行**；OpenAI Agents SDK 真实模型适配器需要人工配置真实 API Key 并额外验证。CI 不访问真实付费模型，不代表生产环境的远端 LLM 已完成验收。

## 一、模块映射

| 代码 | 作用 |
| --- | --- |
| `backend/agent_catalog/` | P1-A 的 Django Agent 定义、版本、权限 API；原模块名 `agents` 会遮蔽 OpenAI SDK 的 `agents` 导入，因此改名，Django AppConfig.label **仍为 agents**，表名及迁移标识保持不变 |
| `backend/agent_runtime/adapter.py` | `MockRuntimeAdapter`、`OpenAIAgentsAdapter`、模型适配器选择 |
| `backend/agent_runtime/engine.py` | 单 Agent 执行控制、模型/工具调用次数、截止时间及步骤追踪 |
| `backend/agent_runtime/tasks.py` | Celery Worker 调用 Runtime，安全保存成功结果或错误码 |
| `backend/tool_gateway/executor.py` | 工具白名单与每次调用重新鉴权，只读合成数据 |
| `backend/agent_runtime/services.py` | 状态机与执行步骤事件序列，支持 P1-C 增量事件 |
| `frontend/src/views/agents/agentRuns.vue` | Agent 执行中心，提交任务、查看状态/结果/步骤/事件 |
| `backend/tests/test_agent_runtime_p1c.py` | Mock 完整闭环、安全拒绝、预算/超时、SDK 导入和无网络 Adapter Smoke |

## 二、部署运行

在 `backend` 目录：

```bash
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py bootstrap_mock_catalog
python manage.py init
```

单独启动三个长期进程：

```bash
python manage.py runserver
celery -A main worker --loglevel=info --concurrency=2
python manage.py dispatch_agent_outbox --interval 2
```

已配置 Redis（默认 Broker DB 3、结果 DB 4）和数据库。默认的 `mock` Provider / `mock-small` 模型不依赖 API Key。管理员在 Agent 管理页创建并发布 Agent，授权使用 `mock_sales_summary`；之后从左侧 **Agent 执行**（`/agentRuns`）提交问题并查看执行结果。

### 示例输入与结果

```json
{
  "agent_id": "<已发布 Agent 的 UUID>",
  "input": {"message": "分析本月销售情况"},
  "deadline_seconds": 120
}
```

通过 REST `POST /api/platform/v1/runs/` 时还必须设置 `Idempotency-Key: <唯一请求键>`。页面会自动生成该值。

Mock 数据固定：2026-09 总额 125000 元，2026-10 为 115000 元（相对下降 8%），数据来源标识 `synthetic:mock_sales_summary`。这**不是**真实 ERP 数据，也不产生任何客户信息或写操作。

最终状态：`SUCCEEDED`；步骤至少包含 `DISPATCH`、`TOOL_READ`、`MODEL_CALL`；事件包含 `run.queued`、`run.started`、`run.step_completed`、`run.completed`。结果含结论、来源和 `mock` 标志，用户可在页面详情查看。

## 三、真实 OpenAI Agents SDK 模式（受控、可选）

已固定依赖 `openai-agents==0.24.0`，通过 `OpenAIAgentsAdapter` 单独封装，非 Mock Provider **不会**默认联网。

真实模式需要由管理员在受信任的后端配置模型元数据：`ModelProvider.adapter_type = "openai"`、`enabled=True`，以及合法可用的 `ModelProfile.model_code`、`enabled=True`；Worker 环境提供 `OPENAI_API_KEY`。**不要**通过前端 API 或数据库写入明文 API Key；建议在生产环境通过 Secret Manager/容器密钥注入。配置前应核对资费、模型区域及模型工具调用兼容性。

SDK 经 `from agents import Agent, Runner, function_tool, RunConfig` 使用；Django 目录改名为 `agent_catalog` 以规避 Python 导入冲突。SDK 管理 LLM 轮次，所有实际工具调用都代理到 `Tool Gateway`，在每次调用时检查当前用户与 Agent ToolGrant/ToolDefinition 是否仍然有效。

安全约束：SDK 默认追踪关闭，防止把敏感 Prompt/工具内容自动上传外部 Tracing 系统；数据库本地 RunStep/RunEvent 不保存原始用户输入和工具完整返回，仅保存已筛选摘要；结果正文保存经过长度限制的返回文本。

**真实模型尚需人工验证**：新建真实 Provider/Profile、配置模型及密钥、实际发起任务并核对账单/Token 与模型输出。自动化测试只验证 SDK 正确导入、无外网 Adapter 调用和错误拒绝分支，不会生成真实 API 费用。

## 四、边界与后续硬化

- 本期只读工具 `mock_sales_summary`，固定虚构数据。参数只支持 `month=2026-09/2026-10`，不支持任意 Python/SQL/HTTP Tool。
- 每次 Tool 调用都重新查询当前 Agent 版本授权、工具启停及用户访问权限，撤销授权后的任务不得继续调用工具。
- Worker 通过 P1-B 的数据库租约抢占；限制最多 5 次工具调用、12 个持久步骤、单次提交总时长 1–270 秒（默认 120 秒），SDK 最多 4 模型轮次。超过限制、安全拒绝和异常只保存安全错误码。
- 当前限制属于**协作式**预算检查，在模型请求内部阻塞时无法立刻取消 HTTP 请求；生产环境还应给 SDK HTTP 客户端配置网络超时与运行中租约续期，长运行必须使用独立 Worker 队列。
- P1-B 的过期租约检测在过期时会标记 FAILED；外部模型仍可能返回，最终写入受租约约束，不能覆盖过期终态。
- 尚无真实模型费用/Token 读取、模型重试分类、模型运行动态暂停、可写工具、工作流编排、人工审批和跨进程实时 SSE/WS 增量流；这些均需后续迭代。

## 五、验收命令

```bash
cd backend
python manage.py check --settings=test_settings
python manage.py makemigrations --check --dry-run --settings=test_settings
pytest -q tests/test_agent_runtime.py tests/test_agent_runtime_p1c.py
cd ../frontend
npm test
npm run build
```

GitHub CI 运行全量 Django/pytest、迁移检查、Redis Worker 联调、Vue Vitest 与 Vite 构建。

## 六、后续建议

**P2-A：模型网关与运行治理**。完成真实 Provider/Profile 配置与密钥引用、Token/成本追踪、外部调用超时与限流、模型使用额度、Run 取消和执行租约续期；再做 Session/Message 与 WebSocket 流式 UI。不得将当前模拟任务或未验证的远端 Provider 称为完整生产级 Agent 平台。
