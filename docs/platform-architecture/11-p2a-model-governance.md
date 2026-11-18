# P2-A · Model Gateway 配置、用量估算与 AgentRun 运行治理

> 实施日期：2026-11-18。此文档区分“GitHub CI 中离线可验证的功能”和“必须在实际部署中手动验证的真实模型行为”。

## 一、交付内容

- `model_gateway.ModelProvider` / `ModelProfile`：管理员配置 OpenAI/Mock Provider、可信环境变量密钥引用、启停、模型 ID、Token 单价与单次输出上限
- `model_gateway.secrets`：只允许 `env:OPENAI_API_KEY` 或 `env:EAH_MODEL_KEY_...` 环境变量引用；数据库/API 不接受或返回 API Key 明文
- `agent_runtime.ModelUsage`：每个 Run 的模型、输入/输出 Token、估算成本、价格快照；**上游未提供用量时记录 NULL，不伪造 0**
- `AgentRun`：新增 `CANCEL_REQUESTED` 状态、排队取消与运行中协作式取消，取消请求只能操作本人 Run 或管理员可见 Run
- `DispatchOutbox`：取消排队任务后标记为 `CANCELLED`，不会继续投递；运行中的取消请求在下一个检查点生效
- Run 入队：每个用户最多 3 条活动（QUEUED/RUNNING/CANCEL_REQUESTED）任务，24 小时内最多 100 条创建记录；并发计数在用户行锁下完成
- SDK Adapter：按 Provider 独立的 `OpenAIProvider(api_key=...)` 而非可变的全局密钥，配置 `ModelSettings(max_tokens=...)`；关闭 SDK 外部 tracing
- 前端：新增 `/modelManage` 配置页面；`/agentRuns` 显示用量/估算费用与协作取消按钮

## 二、部署步骤

```bash
cd backend
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py init
```

保持 Django、Redis、Celery Worker、Outbox Dispatcher 正常运行。模型配置菜单仅应授权给超级管理员；所有 API 再次在后端校验 `is_superuser && is_staff && is_active`。

设置真实密钥时**不要上传 key、不要写入数据库或 GitHub 仓库**：

```bash
# 在实际 Worker 的安全密钥注入环境中设置；不要提交到版本库
export EAH_MODEL_KEY_MAIN="(从 Secret Manager 注入真实密钥)"
```

在「模型配置」中创建：

```json
{
  "code": "openai-main",
  "name": "OpenAI Primary",
  "adapter_type": "openai",
  "secret_ref": "env:EAH_MODEL_KEY_MAIN",
  "enabled": true
}
```

接着创建 ModelProfile：

```json
{
  "provider": 2,
  "name": "企业试运行模型",
  "model_code": "gpt-4o-mini",
  "enabled": true,
  "input_price_per_million": "0.000000",
  "output_price_per_million": "0.000000",
  "max_output_tokens": 512
}
```

以上示例价格 **0 只为演示占位，不代表官方定价**。实际启用付费模型前，应由管理员核对该模型在供应商实际账户的当前价格与计费口径，填写 USD / 100 万 Token 的输入/输出费率；如价格未知，不应把估算费用作为正式财务核算。

## 三、管理与运行 API

管理员专用（`/api/platform/v1/`）：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST | `model-providers/` | Provider 列表、创建 |
| GET/PATCH | `model-providers/{id}/` | 查看/修改、启停、Secret Ref |
| GET/POST | `model-profiles/` | 模型列表、定价、创建 |
| GET/PATCH | `model-profiles/{id}/` | 编辑、启停、修改上限 |

用户 Run 接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `runs/{uuid}/usage/` | 本次模型用量与估算费用；未记录时为 null |
| POST | `runs/{uuid}/cancel/` | 请求协作式取消；返回新的权威 Run 状态 |
| GET | `runs/{uuid}/` | 查询 `CANCEL_REQUESTED` / `CANCELLED` 等状态 |

历史模型单价快照在 **AgentRun 创建时**冻结，避免 Run 期间或事后修改价格影响已提交任务的计费口径。费用按：

```text
estimated_cost_usd = (input_tokens × input_price_per_million
                     + output_tokens × output_price_per_million) / 1000000
```

Decimal 保留 8 位小数，数据库保存使用价格。该金额**不包含**工具调用、缓存折扣、供应商税费、内部加价，且不代替真实账单。

## 四、取消与超时语义

- QUEUED → CANCELLED：事务内标记终态和 Outbox 已取消，Worker 即使收到旧消息也不能 claim。
- RUNNING → CANCEL_REQUESTED：只提出停止请求；Worker 在模型/工具轮次的预算检查处识别；仅原租约持有者可完成终态写入。
- **协作式而非强制中断**：取消无法撤销已发送的模型 API 请求或已经产生的 Token 费用，也不能保证第三方一定中断；迟到的成功结果不会覆盖取消终态。
- 租约覆盖运行 deadline 加短暂缓冲，以减少正常网络调用尚未结束时被回收器误判为 Worker 崩溃的概率。
- 当前只读工具仍不触发企业业务写操作。若未来接入写操作，必须先做审批/幂等/对账，而不能依赖“取消”保证回滚。

## 五、限制与验收要求

**已自动化测试范围**：Provider 权限与密钥拒绝；Token 数值校验、费用价格快照；无用量时 NULL；队列取消不派发、进行中取消与终态竞争；并发任务数量限制；现有 P1-C Mock Agent 回归。

**仍待专项验证**：
- 带真实密钥的 Provider SDK 联网、实际 Token 值与 OpenAI 账单差异；
- 长时间模型调用和取消、供应商网络超时/429/5xx 分类；
- PostgreSQL 下真正同时创建请求的锁竞争测试；
- 运行中租约续期和高可用 Worker 健康监控；
- 用户、部门级配置权限、全局预算/费用阈值告警、会话/长时流式追踪。

测试指令：

```bash
cd backend
python manage.py check --settings=test_settings
python manage.py makemigrations --check --dry-run --settings=test_settings
pytest -q tests/test_agent_runtime_p2a.py tests/test_agent_runtime_p1c.py tests/test_agent_runtime.py
cd ../frontend
npm test
npm run build
```

## 六、下一阶段建议

**P2-B：Session/Message + Run 事件流 + 模型真实联调**。优先完成可持续的上下文与 Session 权限、SSE/WebSocket、RunEvent 游标补偿、Token/成本查询聚合与生产级模型错误分类；禁止使用模拟计费数据冒充供应商实际金额。
