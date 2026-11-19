# -*- coding: utf-8 -*-
"""
种子数据：测试用角色、账号与常见部门（RBAC 验收）。

与 `manage.py init` 分离：init 保持生产安全（不建演示账号/固定密码），
本命令按需执行，仅在测试/演示环境使用：

    python manage.py seed_test_data
    python manage.py seed_test_data --password 'YourPass@2026'

行为：
- 幂等，可重复执行（update_or_create / 先删后建角色菜单权限）；
- 测试账号密码每次执行都会重置为指定值（默认 EahTest@2026）；
- 只管理本命令定义的角色/部门/账号，不影响其他数据。
"""

from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from system.models import Dept, Menu, Role, RoleMenuPermission, Users

DEFAULT_PASSWORD = "EahTest@2026"

ROOT_DEPT_KEY = "enterprise-agent-hub"

# (key, 名称, 父级key, 排序, 负责人)
DEPT_TREE = [
    ("gm-office", "总经办", None, 10, "张总"),
    ("rd", "技术研发部", None, 20, "李研"),
    ("rd-frontend", "前端组", "rd", 21, "王前"),
    ("rd-backend", "后端组", "rd", 22, "刘后"),
    ("rd-qa", "测试组", "rd", 23, "陈测"),
    ("rd-ops", "运维组", "rd", 24, "赵运"),
    ("product", "产品部", None, 30, "周品"),
    ("operation", "运营部", None, 40, "吴运"),
    ("marketing", "市场部", None, 50, "郑市"),
    ("sales", "销售部", None, 60, "冯销"),
    ("finance", "财务部", None, 70, "褚财"),
    ("hr", "人力资源部", None, 80, "卫人"),
    ("admin-affairs", "行政部", None, 90, "蒋行"),
]

# 稳定菜单编码（与 system/initialize.init_menu 一致）
MENU_CODES = {
    "workspace": "4a7a7748387f44dbab72027d8bdc87f7",      # 工作台
    "message": "44662b7fe6b54395994f28ed88eaf3f0",        # 我的消息
    "personal": "98870fbaffb348ab9fd16a88e946bf09",       # 个人中心
    "agent_chat": "eah-agent-chat-p2b",                   # Agent 会话
    "agent_runs": "eah-agent-runs-p1c",                   # Agent 执行
    "agent_manage": "eah-agent-manage-p1a",               # Agent 管理
    "auto_exec": "eah-automation-executions-v1",          # 自动化任务
    "auto_sched": "eah-automation-schedules-v2",          # 定时任务计划
    "org_dir": "af862854dc44410d84b8b2ae5c16c90d",        # 组织与权限（目录）
    "user_mgmt": "31552696153b42599ce1faf6fe495824",      # 用户管理
    "dept_mgmt": "95227fe101e747908c12b56d2bae5e8e",      # 部门管理
    "role_mgmt": "1b5018bdb5e04698b84da505e8a6b93c",      # 角色管理
    "menu_mgmt": "2e9937b37ac94e248e9ed159bfe7b655",      # 菜单管理
    "auth_mgmt": "8faec98030e443b99ce0d4c636163db7",      # 权限管理
    "op_log": "24d2eb79a21141afbe73058cc02545e0",         # 操作日志
    "login_log": "a8b435647f0b4a3f852ec796433e8919",      # 登录日志
    "sys_dir": "563092a536194a1493551a0043f1f1a3",        # 系统配置（目录）
    "model_mgmt": "eah-model-config-p2a",                 # AI 模型管理
    "sys_config": "6354ba32ae734b5eaa799a65f76deee6",     # 平台设置
    "dict": "205910763e0e42fbbc12833d2f7d61bb",           # 数据字典
    "notice": "4f947108c5bf44f2b97e4a80daebf772",         # 通知公告
    "ops": "eah-ops-manage-v1",                           # 运维管理
}

# 数据权限：0 仅本人 / 1 本部门 / 2 本部门及以下 / 4 全部
ROLE_DEFS = [
    {
        "key": "system_admin", "name": "系统管理员", "sort": 10,
        "menus": "*:4",  # 全部菜单、全部数据权限
    },
    {
        "key": "agent_operator", "name": "Agent 运营", "sort": 20,
        "menus": {
            "workspace": 4, "message": 4, "personal": 4,
            "agent_chat": 4, "agent_runs": 4, "agent_manage": 4,
            "auto_exec": 4, "auto_sched": 4,
            "sys_dir": 4, "model_mgmt": 4,
        },
    },
    {
        "key": "dept_manager", "name": "部门管理员", "sort": 30,
        "menus": {
            "workspace": 0, "message": 0, "personal": 0,
            "agent_chat": 0, "agent_runs": 2,  # 本部门及以下
            "org_dir": 2, "user_mgmt": 2, "dept_mgmt": 2,
        },
    },
    {
        "key": "auditor", "name": "审计员", "sort": 40,
        "menus": {
            "workspace": 4, "message": 4, "personal": 4,
            "org_dir": 4, "op_log": 4, "login_log": 4,
        },
    },
    {
        "key": "end_user", "name": "普通用户", "sort": 50,
        "menus": {
            "workspace": 0, "message": 0, "personal": 0,
            "agent_chat": 0, "agent_runs": 0,  # 仅本人数据
        },
    },
]

# (username, 姓名, 角色key, 部门key列表, identity)  identity: 0 超管 / 1 后台 / 2 前端用户
USER_DEFS = [
    ("test_admin", "系统管理员·测试", "system_admin", ["gm-office"], 1),
    ("test_agent_ops", "Agent 运营·测试", "agent_operator", ["rd"], 1),
    ("test_dept_mgr", "部门管理员·测试", "dept_manager", ["rd"], 1),
    ("test_auditor", "审计员·测试", "auditor", ["hr"], 1),
    ("test_user", "普通用户·测试", "end_user", ["rd-frontend"], 1),
    ("test_frontend", "前端用户·测试", "end_user", ["marketing"], 2),
]


class Command(BaseCommand):
    help = "创建测试用角色、账号与常见部门（幂等，仅测试环境使用）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--password", default=DEFAULT_PASSWORD,
            help=f"测试账号统一密码（默认 {DEFAULT_PASSWORD}）",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        password = options["password"]
        menus = self._load_menus()
        self._seed_depts()
        roles = self._seed_roles(menus)
        self._seed_users(roles, password)
        self.stdout.write(self.style.SUCCESS("测试数据种子完成。"))

    # ------------------------------------------------------------------
    def _load_menus(self):
        menus = {}
        for name, code in MENU_CODES.items():
            menu = Menu.objects.filter(code=code).first()
            if menu is None:
                self.stdout.write(self.style.WARNING(
                    f"菜单缺失: {name}({code})，请先执行 python manage.py init"
                ))
            menus[name] = menu
        if all(m is None for m in menus.values()):
            raise CommandError("菜单未初始化，请先执行 python manage.py init")
        return menus

    def _seed_depts(self):
        self.stdout.write("初始化测试部门 ...")
        root, _ = Dept.objects.update_or_create(
            key=ROOT_DEPT_KEY,
            defaults={"name": "平台组织", "sort": 1, "parent": None},
        )
        created = {None: root}
        # 按 parent 在前排序保证两轮内建完（DEPT_TREE 已按此约定排列）
        for key, name, parent_key, sort, owner in DEPT_TREE:
            parent = created.get(parent_key) or (root if parent_key is None else None)
            if parent is None:
                raise CommandError(f"部门父级不存在: {parent_key}")
            dept, _ = Dept.objects.update_or_create(
                key=key,
                defaults={"name": name, "sort": sort, "parent": parent, "owner": owner, "status": True},
            )
            created[key] = dept
        self.stdout.write(f"  部门就绪: {len(created) - 1} 个（含层级）")

    def _seed_roles(self, menus):
        self.stdout.write("初始化测试角色及菜单权限 ...")
        roles = {}
        for defi in ROLE_DEFS:
            role, _ = Role.objects.update_or_create(
                key=defi["key"],
                defaults={"name": defi["name"], "sort": defi["sort"], "status": True,
                          "remark": "测试种子角色（seed_test_data 管理）"},
            )
            roles[defi["key"]] = role
            # 重建该角色的菜单权限（与角色管理页保存逻辑一致：先删后建）
            RoleMenuPermission.objects.filter(role=role).delete()
            if defi["menus"] == "*:4":
                pairs = [(m, 4) for m in menus.values() if m is not None]
            else:
                pairs = [(menus[k], scope) for k, scope in defi["menus"].items()
                         if menus.get(k) is not None]
            for menu, scope in pairs:
                RoleMenuPermission.objects.create(role=role, menu=menu, data_scope=scope)
            self.stdout.write(f"  {defi['name']}({defi['key']}): {len(pairs)} 个菜单")
        return roles

    def _seed_users(self, roles, password):
        self.stdout.write("初始化测试账号 ...")
        self.stdout.write(f"  统一密码: {password}")
        for username, name, role_key, dept_keys, identity in USER_DEFS:
            user, _ = Users.objects.update_or_create(
                username=username,
                defaults={
                    "name": name, "nickname": name, "identity": identity,
                    "email": f"{username}@eah.test",
                    "mobile": None, "gender": 2,
                    "is_active": True, "is_staff": False, "is_superuser": False,
                },
            )
            validate_password(password, user=user)  # 不满足强度要求直接报错回滚
            user.set_password(password)
            user.save(update_fields=["password"])
            user.role.set([roles[role_key]])
            depts = list(Dept.objects.filter(key__in=dept_keys))
            user.dept.set(depts)
            dept_names = "/".join(d.name for d in depts)
            self.stdout.write(
                f"  {username}({name}) -> 角色[{roles[role_key].name}] 部门[{dept_names}] identity={identity}"
            )
