# P1-A 交付说明：Agent 定义、版本、权限与只读目录

> 本文描述 **已提交的 P1-A 后端代码**。它不是 Agent Runtime：不会调用 LLM、执行工具或返回推理结果。P1-B / P1-C 再补运行机制。

## 代码

- `backend/agents/`：Agent、AgentVersion、AgentAccessGrant、ToolGrant，发布服务与 REST API。
- `backend/model_gateway/`：ModelProvider、ModelProfile（凭据只使用 secret_ref，API 永不返回）。
- `backend/tool_gateway/`：ToolDefinition（P1-A 仅准许 mock_sales_summary 的只读定义）。
- 三组 `0001_initial.py` Django migration，不修改 `system`、`automation` 原有表。
- `backend/tests/test_platform_agents.py`：认证、发布不可变、对象授权、实时权限撤销、禁止动态工具调用等。

## 安装与首次演示配置

```bash
cd backend
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py bootstrap_mock_catalog
```

`bootstrap_mock_catalog` 创建 **不含真实 API Key** 的 `mock` Provider、`mock-small` ModelProfile、`mock_sales_summary` 只读 ToolDefinition。重新执行不会重复创建。

当前不支持从 API 写入模型密钥或任意工具代码。真正的模型供应商凭据管理、SDK Adapter、工具执行属于后续阶段。不要将模拟模型当成可计费的真实 LLM。

## 当前 REST API（JWT）

前缀：`/api/platform/v1/`。管理员为已激活、非删除的 **is_staff + is_superuser** 用户；业务用户必须有明确 `AgentAccessGrant(run)`，且 Agent 已发布并激活。

| 方法 | 路径 | 权限/说明 |
| --- | --- | --- |
| GET/POST | `agents/` | 登录用户查看获准 Agent；管理员创建草稿 |
| GET/PATCH | `agents/{uuid}/` | 获准用户读取；管理员修改元数据 |
| GET/POST | `agents/{uuid}/versions/` | 获准用户仅可见已发布版本；管理员创建草稿 |
| GET/PATCH | `agents/{uuid}/versions/{uuid}/` | 管理员可编辑草稿；发布后只读 |
| POST | `agents/{uuid}/versions/{uuid}/publish/` | 管理员发布；验证模型、工具启用 |
| POST | `agents/{uuid}/versions/{uuid}/tools/{id}/revoke/` | 管理员撤销已授权工具，无法恢复已发布授权 |
| GET/POST | `agents/{uuid}/access-grants/` | 管理员查看和授予用户运行权限 |
| DELETE | `agents/{uuid}/access-grants/{id}/` | 管理员撤销用户运行权限 |
| GET | `catalog/models/`, `catalog/tools/` | 可用模型和可见只读工具目录 |
| POST | `provision/providers/` | 仅管理员创建 disabled Provider 元数据；禁止密钥和任意 base_url |
| POST | `provision/tools/` | 仅管理员登记内置 mock_sales_summary 工具 |

创建 Agent：

```http
POST /api/platform/v1/agents/
Content-Type: application/json
Authorization: JWT <token>

{"code":"sales-analysis","name":"销售分析Agent","description":"分析企业虚构销售数据"}
```

创建草稿版本（从 `catalog/models/` 和 `catalog/tools/` 获取真实 ID）：

```json
{
  "system_prompt": "根据授权工具返回的数据进行有依据的只读分析",
  "model_profile": 1,
  "tool_ids": [1]
}
```

版本发布后如需改系统提示词，必须创建新版本；发布后的 ToolGrant 只能撤销，不能新增或恢复。用户运行权限支持单独撤销，P1-C 的 Tool Gateway 必须**每次调用再次读取授权**，不能复用启动时的缓存或快照作为放行条件。

**当前限制**：还没有真实工具调用、模型接入、AgentRun、状态机、Tool 运行沙箱、模型用量成本及完善的企业角色/部门级 Agent 数据权限。当前用户 Grant 是最小的用户对象级 RBAC，不是未来完整治理系统。

## 测试与运维

```bash
cd backend
python manage.py check --settings=test_settings
python manage.py makemigrations --check --dry-run --settings=test_settings
pytest -q tests/test_platform_agents.py
```

平台 API 应使用真实 HTTP 401/403/404/409；不能因旧项目异常处理器返回 HTTP 200 误判成功。

## 下一阶段

**P1-B**：AgentRun、RunStep、RunEvent、DispatchOutbox、状态迁移 CAS、幂等提交、Worker 租约与任务查询。P1-A **不得**为了展示“跑通”而直接用四态 `automation.TaskExecution` 假扮 AgentRun。
