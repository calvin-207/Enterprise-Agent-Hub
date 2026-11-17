"""Enterprise Agent Hub initial menu and account bootstrap regression tests."""
import pytest

from system.initialize import Initialize
from system.models import Menu, Users


@pytest.mark.django_db
def test_menu_initialization_has_real_pages_and_is_idempotent():
    initializer = Initialize()
    initializer.init_menu()
    first_count = Menu.objects.count()
    assert first_count == 15

    expected = {
        "home", "myMessage", "PersonalCenter", "buserManage",
        "deptManage", "roleManage", "menuManage", "authorityManage",
        "journalManage", "loginLogs", "systemConfig",
        "sysDictionary", "messagNotice",
    }
    assert set(Menu.objects.filter(type=1).values_list("component_name", flat=True)) == expected
    assert not Menu.objects.filter(name__in=["功能演示", "iframe嵌套", "外链测试"]).exists()

    custom = Menu.objects.create(code="project-custom", name="Custom", type=0)
    initializer.init_menu()
    assert Menu.objects.count() == first_count + 1
    assert Menu.objects.filter(pk=custom.pk).exists()
    assert not Menu.objects.filter(code="01599f73f61848aa811f687b1cfc1588").exists()


@pytest.mark.django_db
def test_admin_bootstrap_does_not_create_demo_accounts_or_default_password(monkeypatch):
    monkeypatch.delenv("INITIAL_SUPERUSER_PASSWORD", raising=False)
    initializer = Initialize()
    initializer.init_users()
    admin = Users.objects.get(username="SuperAdmin")
    assert admin.is_superuser and admin.is_staff
    assert not admin.has_usable_password()
    assert not Users.objects.filter(username__in=["admin", "guest"]).exists()

    original_password = admin.password
    monkeypatch.setenv("INITIAL_SUPERUSER_PASSWORD", "SomeNewStrongPassword!2026")
    initializer.init_users()
    admin.refresh_from_db()
    assert admin.password == original_password


@pytest.mark.django_db
def test_menu_buttons_reference_existing_initialized_menus():
    initializer = Initialize()
    initializer.init_menu()
    initializer.init_menu_button()
    initializer.init_menu_button()
