# AI 模型管理与供应商同步模型（V1）

> 适用：Enterprise-Agent-Hub。模型管理位于 **系统配置 → AI 模型管理**，路由保持 `/modelManage` 不变。保留所有已有 ModelProvider、ModelProfile、AgentVersion 及成本记录。模型同步和真实推理能力应分别验证。

## 管理流程

1. 平台超级管理员进入 **系统配置 → AI 模型管理 → 模型提供商**。
2. 创建供应商：
   - 官方 OpenAI：选择 `openai`，模型列表来自 OpenAI 官方 API。
   - OpenAI 兼容 API：选择 `openai_compatible`，Base URL 须为 HTTPS 且域名在运维白名单中；是否实际兼容 SDK 要单独验证。
   - Mock：选择 `mock`，用于无网络测试。
3. 选择凭据保存方式（两种互斥）：
   - **环境变量引用**：`env:OPENAI_API_KEY` 或 `env:EAH_MODEL_KEY_MAIN`，API Key 放在后端与 Worker 的安全运行环境。
   - **后台加密录入**：通过 write-only `api_key` 字段写入，使用单独的 `EAH_MODEL_ENCRYPTION_KEY` 加密后存库；查询只返回 `has_stored_key`，不会回传 Key。
4. 启用 Provider，点击 **同步模型**；服务端访问供应商 `GET /v1/models`（由 SDK 的 `models.list()` 实现），写入本地 ModelProfile。
5. 在 **模型列表与价格** 页筛选/编辑同步模型，设置名称、输入/输出 Token 估算单价、输出上限、启用状态，以及平台默认模型。
6. 在 Agent 管理页创建新 AgentVersion，系统预选默认模型，管理员可更换。只有已启用模型能被选择并用于发布。

**同步规则：**

- 新发现模型：`source=sync`、`enabled=false`、`is_default=false`、价格为 0（**未知价格占位，不等于免费**）。
- 已存在模型：只刷新 `last_seen_at`，**绝不覆盖**已有名称、价格、启停、默认模型、或已发布 Agent 的模型关联。
- 上游模型列表缺失或同步失败：本地模型**不删除、不自动停用**；`last_sync_at` 仅成功后刷新。
- 去重依据是 `(provider_id, model_code)` 唯一约束，重复点击“同步模型”不会重复插入。
- 供应商列出的 ID 不一定具备聊天/函数调用能力；不自动启用，也不自动决定价格/上下文能力。实际启用前应跑兼容性检查。
- 模型列表同步仅限当前支持的 OpenAI 格式返回 `data[*].id`；原生 Anthropic/Gemini 等未提供兼容接口的供应商需要独立 Discovery Adapter。

## API

沿用 `/api/platform/v1/`：

| HTTP | 路径 | 说明 |
| --- | --- | --- |
| GET/POST | `model-providers/` | Provider 列表/创建；仅超级管理员 |
| GET/PATCH | `model-providers/{id}/` | 编辑供应商（支持 `base_url`, `secret_ref`, write-only `api_key`, `clear_api_key`） |
| POST | `model-providers/{id}/sync/` | 主动同步模型，返回 total / created / existing / last_sync_at |
| GET/POST | `model-profiles/` | 模型目录/手动创建 |
| GET/PATCH | `model-profiles/{id}/` | 配置启停、单价、默认标记 |
| GET | `catalog/models/` | 已启用模型供 Agent 草稿版本选择（包含 is_default） |

同步成功示例：

```json
{
  "code": 2000,
  "msg": "success",
  "data": {
    "total": 12,
    "created": 8,
    "existing": 4,
    "last_sync_at": "2026-11-18T06:00:00"
  }
}
```

## 凭据加密配置

使用独立 Fernet 密钥，**不能把它填入前端或提交 Git**。在受信任的部署机器上生成：

```bash
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

将结果存入 Secret Manager，通过 `EAH_MODEL_ENCRYPTION_KEY` 注入 Django API 及执行 Worker。所有节点需使用**同一加密密钥**。丢失该密钥将无法解密已存储 API Key。密钥轮换需要先实现重加密流程；不要直接修改环境值。

兼容服务的 HTTP 主机白名单（示例）：

```bash
# 由运维设置；不要允许任意主机或通配符
export EAH_MODEL_ALLOWED_HOSTS="api.vendor-example.com"
```

第三方必须提供完整 HTTPS `.../v1` Base URL、公开路由 IP 且在白名单中。同步网络客户端禁止 HTTP 重定向、重试次数为 0，最多 8 秒超时，模型列表最多 1000 个。建议生产环境额外在网关层配置 egress ACL/DNS 防重绑定策略。

**API Key 安全边界**：管理员只能写入或清除密钥，不能读取原文；加密存库的密钥仍需要通过运行进程解密，具备服务器权限的管理员仍可接触密钥。模型密钥访问审计与更复杂的轮换机制属于后续安全增强。

## 回归验证

```bash
cd backend
pip install -r requirements.txt
python manage.py migrate
python manage.py init
pytest -q tests/test_model_sync.py
pytest -q
python manage.py makemigrations --check --dry-run --settings=test_settings
cd ../frontend && npm test && npm run build
```

测试覆盖：Mock 重复同步、已配置价格/启停不覆盖、真实供应商模型列表模拟导入、超级管理员权限、密钥加密/非回显、白名单和私网地址拒绝、供应商报错后保留本地数据、默认模型全局唯一。

**限制**：真实 OpenAI 供应商需要管理员自己的合法 API Key 才能实际同步；CI 不请求真实收费 API，也不声称已完整验证所有兼容供应商。模型同步本身是只读目录操作，不会主动执行付费推理或开通供应商服务。
