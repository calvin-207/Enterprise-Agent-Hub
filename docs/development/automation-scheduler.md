# 自动化任务 V2：任务定义 + Cron 计划 + Celery Beat

本阶段在 V1 的 `TaskExecution` 上新增任务定义、持久化 Cron 计划和计划管理页面。调度基于 **django-celery-beat 2.9.0**，保存或启停计划时同步更新 `django_celery_beat_periodictask`；Beat 无需依赖静态配置文件读取这些计划。

## 组成

```text
Vue: /taskSchedules
  ├── 任务定义（TaskDefinition）
  │     └── 当前白名单：ping、database_probe
  └── Cron 计划（TaskSchedule）
        ├── minute / hour / day_of_month / month_of_year / day_of_week
        ├── enabled
        └── django-celery-beat PeriodicTask
                    |
            DatabaseScheduler（单实例）
                    |
               Redis Broker
                    |
                Celery Worker
           automation.trigger_schedule
                    |
           TaskExecution（唯一 schedule + minute）
                    |
           automation.execute
                    |
           V1 任务记录与详情页面
```

## 初次升级和启动

按照现有 `backend/config.py` 配置数据库和 Redis，然后：

```bash
cd backend
pip install -r requirements.txt
python manage.py migrate
python manage.py init     # 安装“定时任务计划”菜单；不会重置已存在管理员密码
```

分别运行三个独立进程（开发环境可使用三个终端）：

```bash
# 1. Django API
python manage.py runserver 127.0.0.1:8000

# 2. 异步 Worker
celery -A main worker --loglevel=info --concurrency=2

# 3. 数据库驱动的 Celery Beat（整个环境必须且只能有一个实例）
celery -A main beat --scheduler django_celery_beat.schedulers:DatabaseScheduler --loglevel=info
```

如果没有运行 Beat，前端保存的 Cron 计划**不会自动触发**；如果没有运行 Worker，任务只会排队而不会执行。确认 `main/settings.py` 里的 Redis Broker 指向同一个 Redis。

**时区**：当前项目 Django `TIME_ZONE=Asia/Shanghai`、`USE_TZ=False`，Cron 计划使用 Asia/Shanghai 业务时区，不提供逐条选择时区。切换全局时区后要重新评估已有计划的下次执行时间和 `last_run_at`。

## 前端操作

进入左侧菜单 **定时任务计划**（`/taskSchedules`）：

1. 在“任务定义”页创建一个定义，例如“每天检测数据库”，类型选择“数据库连通性检测”；
2. 切到“定时计划”，选择对应定义；
3. 选择预置“每天 09:00”，或按五个字段填写 Cron；
4. 打开“启用此计划”，保存；
5. 如需立即验证，可点击“立即运行”；任务结果前往“自动化任务”页面查看。

提供常用预设：每 5 分钟、每天 09:00、工作日 09:00、每周一 09:00。Cron 的格式为：

```text
分钟 小时 每月日期 月份 星期
0    9     *       *     1-5    # 每个工作日上午 9 时
*/5  *     *       *     *      # 每 5 分钟
```

服务器使用 Celery 原生 Cron 解析器验证字段，不允许通过前端直接指定 Celery 任务函数、队列、args/kwargs 或 Python 代码。

## API（超级管理员限定）

| 方法 | 路径 | 操作 |
| --- | --- | --- |
| GET / POST | `/api/automation/definitions/` | 列出 / 创建任务定义 |
| GET / PATCH / DELETE | `/api/automation/definitions/{id}/` | 查看 / 编辑 / 删除定义 |
| GET / POST | `/api/automation/schedules/` | 列出 / 创建 Cron 计划 |
| GET / PATCH / DELETE | `/api/automation/schedules/{id}/` | 查看 / 编辑 / 删除计划 |
| POST | `/api/automation/schedules/{id}/run/` | 手动执行计划，生成 V1 执行记录 |

当前仅激活的员工超级管理员可以使用。相关操作会在数据库中保存创建人，且不允许自定义可执行代码。删除计划会从 Beat 中移除对应的 PeriodicTask；删除任务定义会移除其关联计划，历史执行记录仍保留。

## 重要的可靠性边界

- 定时消息由 Beat 产生，执行任务由 Worker 消费，**数据库执行记录**提供可审计的结果。
- 同一计划同一分钟重复触发会被数据库唯一约束拒绝，防止双重提交；仍须遵守“一个环境仅运行一个 Beat”。
- 定时任务只能执行白名单里的任务类型。暂停定义会同步暂停关联的 Beat 计划，重新启用定义会恢复原本启用的计划。
- 用户手动点击“立即运行”是一次独立执行，不占 Cron 时间槽。
- 对于真实业务任务，后续还必须实现可恢复的业务幂等、超时补偿、失败告警、审计事件及权限范围校验，不能将 V2 检测任务当作通用代码执行器。
- 当前尚无持久化的任务日志全文、复杂任务编排、暂停正在运行的任务或分布式高可用 Beat。
- 高可用环境要使用数据库主实例和一致的时钟，避免分钟边界附近发生重复投递。

## 开发与验证

```bash
cd backend
python manage.py makemigrations --check --dry-run
python manage.py check
pytest -q tests/test_automation_scheduling.py tests/test_automation_api.py
```

GitHub CI 运行 SQLite 迁移与后端单元测试，并用独立 Redis、Celery Worker 验证异步消息链路。对于 PostgreSQL/MySQL 生产部署，仍应进行实际数据库集成测试。
