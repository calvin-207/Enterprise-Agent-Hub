# -*- coding: utf-8 -*-
"""seed_test_data 命令契约：测试角色/账号/部门种子与 RBAC 菜单解析。"""
import pytest
from django.contrib.auth import authenticate
from django.core.management import call_command

from system.models import Dept, Menu, Role, RoleMenuPermission, Users

PASSWORD = "EahTest@2026"


@pytest.fixture
def seeded(db):
    call_command("init", "-y")
    call_command("seed_test_data", "--password", PASSWORD)


@pytest.mark.django_db
def test_seed_creates_depts_roles_users(seeded):
    assert Dept.objects.filter(key="rd-frontend", parent__key="rd").exists()
    assert Role.objects.filter(key="system_admin").exists()
    assert Role.objects.filter(key="end_user").exists()

    test_user = Users.objects.get(username="test_user")
    assert test_user.identity == 1
    assert list(test_user.role.values_list("key", flat=True)) == ["end_user"]
    assert list(test_user.dept.values_list("key", flat=True)) == ["rd-frontend"]

    frontend = Users.objects.get(username="test_frontend")
    assert frontend.identity == 2


@pytest.mark.django_db
def test_seed_is_idempotent(seeded):
    counts = (
        Dept.objects.count(),
        Role.objects.count(),
        Users.objects.count(),
        RoleMenuPermission.objects.count(),
    )
    call_command("seed_test_data", "--password", PASSWORD)
    assert (
        Dept.objects.count(),
        Role.objects.count(),
        Users.objects.count(),
        RoleMenuPermission.objects.count(),
    ) == counts


@pytest.mark.django_db
def test_seeded_accounts_can_authenticate(seeded):
    for username in ("test_admin", "test_agent_ops", "test_dept_mgr",
                     "test_auditor", "test_user", "test_frontend"):
        assert authenticate(username=username, password=PASSWORD) is not None, username


@pytest.mark.django_db
def test_role_menu_scopes(seeded):
    # 系统管理员：全部菜单、全部数据权限
    admin_role = Role.objects.get(key="system_admin")
    assert admin_role.role_menu_permission.count() == Menu.objects.count()
    assert admin_role.role_menu_permission.filter(data_scope=4).count() == Menu.objects.count()

    # 普通用户：仅基础菜单，且仅本人数据权限
    end_role = Role.objects.get(key="end_user")
    end_menus = set(end_role.role_menu_permission.values_list("menu__code", flat=True))
    assert end_menus == {
        "4a7a7748387f44dbab72027d8bdc87f7",  # 工作台
        "44662b7fe6b54395994f28ed88eaf3f0",  # 我的消息
        "98870fbaffb348ab9fd16a88e946bf09",  # 个人中心
        "eah-agent-chat-p2b",                # Agent 会话
        "eah-agent-runs-p1c",                # Agent 执行
    }
    assert end_role.role_menu_permission.filter(data_scope=0).count() == 5

    # 部门管理员：用户/部门管理为本部门及以下数据权限
    dept_role = Role.objects.get(key="dept_manager")
    user_mgmt = dept_role.role_menu_permission.get(
        menu__code="31552696153b42599ce1faf6fe495824")
    assert user_mgmt.data_scope == 2

    # Agent 运营不包含组织权限菜单
    ops_role = Role.objects.get(key="agent_operator")
    ops_menus = set(ops_role.role_menu_permission.values_list("menu__code", flat=True))
    assert "8faec98030e443b99ce0d4c636163db7" not in ops_menus  # 权限管理
    assert "eah-agent-manage-p1a" in ops_menus
