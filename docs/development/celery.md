# Celery 异步任务与定时调度接入

Enterprise Agent Hub 使用 **Django + Celery + Redis** 作为后台自动化任务的基础执行通道：

```text
Django API / Agent Service
          |
          | task.apply_async() / task.delay()
          v
      Redis DB 3 (Broker)
          |
          v
     Celery Worker
          |
          +--> Django / business services
          |
          v
      Redis DB 4 (task results)

Celery Beat (optional, one instance only)
          |
          +--> schedules tasks into Redis DB 3
```

## 启动步骤（开发环境）

Python 3.11+，准备 Redis 服务。复制现有配置：

```bash
cd backend
cp config.py_template config.py    # 首次运行；数据库与 Redis 配置按实际修改
python -m pip install -r requirements.txt
python manage.py migrate
```

三个不同终端分别运行：

```bash
# 终端 1：Django
python manage.py runserver 127.0.0.1:8000

# 终端 2：Celery Worker（Linux/macOS）
celery -A main worker --loglevel=info --concurrency=2

# 终端 3：Celery Beat（仅当需要周期任务时）
celery -A main beat --scheduler django_celery_beat.schedulers:DatabaseScheduler --loglevel=info
```

Beat 从数据库中读取任务定义和 Cron 计划；在“定时任务计划”前端管理页保存计划后，无需重启 Beat。\n\n旧的 `CELERY_ENABLE_HEALTHCHECK_SCHEDULE=true` 只用于启用静态演示健康检查；**不是**动态计划的必要条件。

生产部署应使用进程管理器或容器分别启动 Django、Worker、Beat。每个部署环境**只允许一个 Beat 调度器**，避免重复派发。Windows 开发优先使用 Docker/Linux Worker。

## 配置

在 `backend/main/settings.py` 中：

| 配置 | 默认值 | 用途 |
| --- | --- | --- |
| `CELERY_BROKER_URL` | `<REDIS_URL>/3` | Redis Broker |
| `CELERY_RESULT_BACKEND` | `<REDIS_URL>/4` | 任务结果存储 |
| `CELERY_TASK_DEFAULT_QUEUE` | `default` | 默认队列 |
| `CELERY_TASK_SOFT_TIME_LIMIT` | 270 秒 | 软超时，尽量触发清理 |
| `CELERY_TASK_TIME_LIMIT` | 300 秒 | 硬超时 |
| `CELERY_RESULT_EXPIRES` | 86400 秒 | 结果有效期 |
| `CELERY_BEAT_SCHEDULER` | `django_celery_beat.schedulers:DatabaseScheduler` | 数据库存储的 Cron 计划调度器 |\n| `CELERY_ENABLE_HEALTHCHECK_SCHEDULE` | false | 可选静态的 15 分钟健康探测 |

Redis DB 0、1、2 已由 Django 缓存使用；默认 3、4 给 Celery。生产环境推荐独立 Redis 或 ACL，不要把 Redis 直接暴露公网。

通过进程环境变量覆盖，示例：

```bash
export CELERY_BROKER_URL=redis://127.0.0.1:6379/3
export CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/4
```

## 立即投递并获取结果

打开 Django shell：

```bash
python manage.py shell
```

```python
from system.tasks import ping

result = ping.delay()             # 仅派发，不在 Web 线程执行
print(result.id)                  # 可用于后续查询结果
print(result.get(timeout=15))     # 仅在运维验证中阻塞等待；API 请求不要这样做
```

`system.tasks.ping` 是无副作用的完整消息链路探针。另有 `system.tasks.check_database` 可用于可选周期探测。二者都不会创建 Agent 或执行业务操作。

## 编写业务任务（推荐方式）

把 Celery 任务放到各 Django 应用的 `tasks.py`，由 autodiscover_tasks 自动发现：

```python
from celery import shared_task
from django.db import transaction

@shared_task(
    bind=True,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def sync_external_record(self, record_id):
    # 示例：传入记录 ID，不要把密钥、模型对象或完整客户数据放进消息。
    # 业务层必须按记录 ID 做幂等，避免 Worker 重试产生重复写入。
    ...
```

数据库事务内派发任务要避免 Worker 比事务提交更早读取数据：

```python
from django.db import transaction
from myapp.tasks import sync_external_record

transaction.on_commit(lambda: sync_external_record.delay(record_id))
```

**重要限制**：Redis + Celery 主要提供异步传递/执行，不能保证“严格只执行一次”。可靠 Agent 任务需建立数据库任务记录、状态机、幂等键、超时恢复、审批与审计。外部业务调用必须在权限验证后执行；禁止把用户提供的任意任务名直接映射到 Celery 调用。

对于长时间运行的 Agent 执行，建议按步骤拆分任务，每一步持久化状态，而非依赖单个不受控的超长 Worker 任务。必要时为不同安全级别的工具调用设置独立队列和 Worker。

## 测试

```bash
cd backend
pytest -q tests/test_celery_integration.py
celery -A main inspect registered
```

GitHub Actions 的 backend Job 额外启动 Redis 服务与独立 Celery Worker，向 Broker 投递 `system.ping` 并实际读取结果。

**当前已提供**通用任务执行记录 API 与前端页面，以及数据库持久化的任务定义 / Cron 计划管理。详见 [自动化任务 V2](./automation-scheduler.md)。Agent 业务执行逻辑仍需后续开发。
