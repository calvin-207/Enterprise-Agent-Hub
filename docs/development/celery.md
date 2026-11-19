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

三个不同终端分别运行（三个进程保持相同的 `HUB_ENV`，队列名与消息匹配由它自动推导）：

```bash
# 终端 1：Django
python manage.py runserver 127.0.0.1:8000

# 终端 2：Celery Worker（Linux/macOS；不加 -Q，自动只消费 hub-<HUB_ENV> 队列）
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
| `CELERY_ENV_TAG` | `prod`（非 DEBUG）/ `dev`（DEBUG），可用 `HUB_ENV` 覆盖 | 环境标签，队列名与消息头都由它推导 |
| `HUB_CODE_VERSION` | `HUB_CODE_VERSION` 环境变量 > git 短哈希 > `backend/VERSION` 文件 | 代码版本戳，防止旧版 Worker 消费新消息 |
| `CELERY_TASK_DEFAULT_QUEUE` | `hub-<环境标签>` | 默认队列（不再写死 `default`） |
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

## 环境与版本匹配（防串环境 / 防旧版 Worker）

多个部署共用同一个 Redis Broker 时（例如本地开发与正式环境指向同一 Redis），会出现两类事故：
**测试任务流进正式环境**，或**代码已更新但未重启的旧 Worker 消费了新版本消息**。平台通过三层机制防护：

1. **队列物理隔离**：默认队列为 `hub-<环境标签>`（`HUB_ENV` 环境变量，默认 `prod`/`dev`）。
   Django API、Beat、Outbox 的发布和 Worker 的消费全部从同一份 settings 推导队列名，
   Worker 不加 `-Q` 就只消费本环境的队列，测试消息物理上进不了正式队列。
2. **消息版本戳**：`before_task_publish` 信号给每条消息盖 `hub-env` / `hub-version` 头。
   Worker 执行前校验：环境不符 → 拒绝执行并丢弃（CRITICAL 日志）；版本不符 →
   任务记录标记 FAILED 并写明两边版本，可在「自动化任务」页面一键重试。
3. **计划归属**：`TaskSchedule.environment` 记录计划归属的环境；`trigger_schedule`
   只执行本环境的计划，其他环境的 Beat 即使误发消息也不会触发。

运维可见性：「运维管理」页面的 Worker 列表显示每个 Worker 上报的环境与版本，
与本服务不一致时标记「不匹配」告警；`system.ping` 的返回值也带 `env` / `version`，
CI 冒烟测试据此断言消息与 Worker 同源。

**运维要点**：

- 每套环境的 Django / Worker / Beat 进程要设置**相同的 `HUB_ENV`**（同一 shell 启动即可继承）；
- 拉取代码后必须**重启 Worker 和 Beat**，否则旧进程会因版本戳不一致拒绝执行新消息；
- 版本来源默认取 git 短哈希；生产构建若剥离了 `.git`，用 `HUB_CODE_VERSION` 环境变量
  或 `backend/VERSION` 文件固定版本号；
- 升级到本机制前残留在旧 `default` 队列中的消息不会有消费者，请评估是否需要人工处理。

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
