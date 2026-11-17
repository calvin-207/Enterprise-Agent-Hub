# 自动化任务管理（P0）

自动化任务管理已接通前端、Django API、数据库执行记录和 Celery Worker。

## 页面与权限

- 菜单：**自动化任务**，路由 `/taskExecutions`，组件 `frontend/src/views/automation/taskExecutions.vue`
- 首版仅**已登录且激活的超级管理员**可访问 `/api/automation/` 下的任务 API；菜单初始化不自动授予普通角色。不要通过前端隐藏按钮代替后端鉴权
- 可用操作：查看分页列表及状态汇总、查看详情、提交预定义检测任务、针对失败记录创建新重试记录
- 状态：`queued`、`running`、`success`、`failed`；列表有待处理任务时每五秒刷新

## 首次部署

```bash
cd backend
cp config.py_template config.py  # 若尚不存在
pip install -r requirements.txt
python manage.py migrate
python manage.py init            # 更新菜单（已有账户不会被重置）
celery -A main worker --loglevel=info --concurrency=2
```

保持 Redis 可用；API 服务和 Worker 必须使用同一数据库与 Redis Broker（默认 Redis DB 3）。迁移将创建 `automation_taskexecution` 表。

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/automation/executions/?page=1&limit=10&status=` | 执行列表、分页、状态计数 |
| GET | `/api/automation/executions/{id}/` | 单条执行详情 |
| POST | `/api/automation/executions/` | 手动提交检测任务 |
| POST | `/api/automation/executions/{id}/retry/` | 仅重试状态为 failed 的任务（生成新记录） |

创建任务的 JSON 示例：

```json
{"task_type": "ping"}
```

允许的任务类型仅包括 `ping`（Worker 连通性）与 `database_probe`（数据库连通性）。服务端使用固定白名单，不允许客户端指定任意 Celery 任务名、函数或 Python 代码。

## 安全与可靠性

- 创建执行记录后在数据库事务提交时才派发消息，防止 Worker 在记录写入前执行
- 任务使用数据库状态条件更新从 `queued` 转为 `running`，同一记录重复投递不会再次执行
- Redis 派发失败时将当前记录标记为 `failed`；不会以 API 响应泄露 Redis 凭据
- 首版失败重试仅为人工操作，并产生独立执行记录，保留历史；不提供任意业务重试或取消
- 数据库记录是状态真相来源，不依赖 Redis 结果长期保存

**仍未包括**：任意业务任务编排、Celery Beat 定时计划管理 UI、执行日志流、Worker 心跳监控、取消/超时回收、细粒度 RBAC 和真正的 Agent Runtime。这些应在后续阶段设计，不要把检测任务视为完整生产调度平台。

## 测试

```bash
cd backend
pytest -q tests/test_automation_api.py tests/test_enterprise_initialize.py
```

GitHub Actions 还会启动 Redis 和 Celery Worker，验证独立 Worker 的任务投递与结果读取。
