## 注意事项
- config.py中可配置支持SQLITE3、POSTGRESQL（安装psycopg2库）
- 如需集成部署后端前端页面，请在前端项目根目录下执行 npm run build:backend，会自动打包静态文件到```backend/frontend/admin```目录中

## 安装依赖环境

```
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

## ️执行迁移命令：(使用sql脚本直接导入可忽略本步骤)

```
# 生成迁移文件
python manage.py makemigrations
# 执行迁移
python manage.py migrate
```

## 初始化数据（Enterprise Agent Hub）

默认只创建 `SuperAdmin` 超级管理员账户，不再创建 `admin` / `guest` 演示账户，也不会设置公共默认密码。初始化是幂等的，不会重置已有管理员密码。

首次安装可使用环境变量设置**唯一且足够强**的管理员密码：

```bash
export INITIAL_SUPERUSER_PASSWORD='替换为你自己的高强度密码'
python manage.py init
unset INITIAL_SUPERUSER_PASSWORD
```

也可以不设置环境变量，先执行 `python manage.py init`，随后运行 `python manage.py changepassword SuperAdmin` 创建初始密码。

仅初始化已开发功能的菜单，包括工作台、组织与权限、Agent 管理、Agent 执行、Agent 会话、模型配置、自动化任务、定时计划和系统设置。模型配置操作仅允许平台超级管理员；Agent 运行权限需要单独授权。

不要在已有业务数据库上使用 `python manage.py init -y` 进行破坏性重置。

## 🚦启动项目（管理员：SuperAdmin；密码由首次初始化时独立设置）

```
#开发服务器方式
python manage.py runserver 127.0.0.1:8000

#ASGI 部署方式（支持 WebSocket）
或使用 daphne (需要使用此asgi方式部署来支持websocket):

daphne -b 0.0.0.0 -p 8000 --proxy-headers main.asgi:application

```

## Celery 后台任务与定时调度

项目已集成 Celery + Redis，需与 Django 服务**分别启动** Worker 和（按需）Beat：

```bash
celery -A main worker --loglevel=info --concurrency=2
# 单独运行数据库调度 Beat（一个环境仅部署一个）
celery -A main beat --scheduler django_celery_beat.schedulers:DatabaseScheduler --loglevel=info
```

使用 `python manage.py shell` 运行 `from system.tasks import ping; ping.delay()` 验证任务派发。详见 [Celery 配置、部署与任务开发说明](../docs/development/celery.md) 和 [定时任务计划 V2 使用指南](../docs/development/automation-scheduler.md)。

## P2-A 模型与执行治理\n\n管理员可从左侧“模型配置”页面配置 Provider（只填 env: 变量引用，禁止输入 API Key 明文）、模型价格和输出限制。用户在“Agent 执行”页面可取消排队或运行中任务并查看 Token/估算费用。详见 [P2-A 使用说明](../docs/platform-architecture/11-p2a-model-governance.md)。\n
## P2-B 持久会话与执行事件流

后台新增“Agent 会话”（`/agentChat`）管理页面，支持连续追问、历史消息、上下文和 SSE RunEvent 状态订阅。消息仅会话所有者可访问。首次升级请执行 `python manage.py migrate` 和 `python manage.py init`，确保 Celery Worker 及 Outbox Dispatcher 持续运行。当前 SSE 是执行状态事件，不是模型 Token 逐字流。详见 [P2-B 部署与验收文档](../docs/platform-architecture/12-p2b-session-and-event-stream.md)。
