import os

import django
from django.db import transaction

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")
django.setup()

from system.models import (
    Dept,
    Button,
    Menu,
    MenuButton,
    Role,
    Users,
    SystemConfig,
    Dictionary,
)


class Initialize:
    def __init__(self, delete=False):
        """
        :param delete: 是否删除已初始化数据
        """
        self.delete = delete
        self.creator_id = "0"

    def save(self, obj, data: list, name):
        """通用保存方法"""
        print(f"正在初始化【{name}】")

        if self.delete:
            try:
                obj.objects.filter(
                    id__in=[ele.get("id") for ele in data if ele.get("id")]
                ).delete()
            except Exception as e:
                print(f"删除{name}数据时出错: {str(e)}")

        for ele in data:
            m2m_dict = {}
            new_data = {}

            for key, value in ele.items():
                if isinstance(value, list):
                    m2m_dict[key] = value
                else:
                    new_data[key] = value

            try:
                object, created = obj.objects.update_or_create(
                    id=ele.get("id"), defaults=new_data
                )

                for key, m2m in m2m_dict.items():
                    m2m = list(set(m2m))
                    if m2m and m2m[0]:
                        m2m_field = getattr(object, key)
                        m2m_field.set(m2m)

            except Exception as e:
                print(f"保存{name}数据时出错(ID:{ele.get('id')}): {str(e)}")

        print(f"初始化完成【{name}】")

    def init_dept(self):
        """创建平台组织根节点，不预设虚构的研发/财务部门。"""
        print("====================== begin init dept ======================")
        Dept.objects.update_or_create(
            key="enterprise-agent-hub",
            defaults={"name": "平台组织", "sort": 1, "parent": None},
        )
        print("====================== end init dept ======================")

    def init_button(self):
        """初始化权限表标识"""
        print('====================== begin button ======================')
        btns = [
            {"name": "编辑", "value": "Update"},
            {"name": "删除", "value": "Delete"},
            {"name": "详情", "value": "Detail"},
            {"name": "新增", "value": "Create"},
            {"name": "查询", "value": "Search"},
            {"name": "保存", "value": "Save"},
            {"name": "导出", "value": "Export"},
            {"name": "导入", "value": "Import"},
            {"name": "重置密码", "value": "ResetPass"},
            {"name": "修改密码", "value": "ChangePass"},
            {"name": "禁用", "value": "Disable"},
            {"name": "日志", "value": "Logs"},
            {"name": "移动", "value": "Move"},
            {"name": "设置状态", "value": "SetStatus"},
        ]
        for it in btns:
            Button.objects.update_or_create(name=it["name"],defaults=it)
        print('====================== end button ======================')


    def init_menu(self):
        """初始化已有功能的菜单；使用稳定 code、重复执行安全。

        不预创建还没有页面与 API 的 Agent/工具/审批入口；
        自定义菜单不在管理范围内，重跑不会清空它们。
        """
        print("====================== begin init menu ======================")
        menu_definitions = [
            {"code": "4a7a7748387f44dbab72027d8bdc87f7", "parent_code": None, "icon": "House", "name": "工作台", "sort": 10, "type": 1, "web_path": "/home", "component_name": "home"},
            {"code": "44662b7fe6b54395994f28ed88eaf3f0", "parent_code": None, "icon": "Message", "name": "我的消息", "sort": 20, "type": 1, "web_path": "/myMessage", "component_name": "myMessage"},
            {"code": "98870fbaffb348ab9fd16a88e946bf09", "parent_code": None, "icon": "User", "name": "个人中心", "sort": 30, "type": 1, "web_path": "/PersonalCenter", "component_name": "PersonalCenter"},
            {"code": "af862854dc44410d84b8b2ae5c16c90d", "parent_code": None, "icon": "Setting", "name": "组织与权限", "sort": 60, "type": 0, "web_path": "/dirsettingsDirs", "component_name": ""},
            {"code": "31552696153b42599ce1faf6fe495824", "parent_code": "af862854dc44410d84b8b2ae5c16c90d", "icon": "User", "name": "用户管理", "sort": 10, "type": 1, "web_path": "/buserManage", "component_name": "buserManage"},
            {"code": "95227fe101e747908c12b56d2bae5e8e", "parent_code": "af862854dc44410d84b8b2ae5c16c90d", "icon": "OfficeBuilding", "name": "部门管理", "sort": 20, "type": 1, "web_path": "/deptManage", "component_name": "deptManage"},
            {"code": "1b5018bdb5e04698b84da505e8a6b93c", "parent_code": "af862854dc44410d84b8b2ae5c16c90d", "icon": "UserFilled", "name": "角色管理", "sort": 30, "type": 1, "web_path": "/roleManage", "component_name": "roleManage"},
            {"code": "2e9937b37ac94e248e9ed159bfe7b655", "parent_code": "af862854dc44410d84b8b2ae5c16c90d", "icon": "Menu", "name": "菜单管理", "sort": 40, "type": 1, "web_path": "/menuManage", "component_name": "menuManage"},
            {"code": "8faec98030e443b99ce0d4c636163db7", "parent_code": "af862854dc44410d84b8b2ae5c16c90d", "icon": "Lock", "name": "权限管理", "sort": 50, "type": 1, "web_path": "/authorityManage", "component_name": "authorityManage"},
            {"code": "24d2eb79a21141afbe73058cc02545e0", "parent_code": "af862854dc44410d84b8b2ae5c16c90d", "icon": "Document", "name": "操作日志", "sort": 60, "type": 1, "web_path": "/journalManage", "component_name": "journalManage"},
            {"code": "a8b435647f0b4a3f852ec796433e8919", "parent_code": "af862854dc44410d84b8b2ae5c16c90d", "icon": "Tickets", "name": "登录日志", "sort": 70, "type": 1, "web_path": "/loginLogs", "component_name": "loginLogs"},
            {"code": "563092a536194a1493551a0043f1f1a3", "parent_code": None, "icon": "Tools", "name": "系统配置", "sort": 70, "type": 0, "web_path": "/systemToolsMgDirs", "component_name": ""},
            {"code": "6354ba32ae734b5eaa799a65f76deee6", "parent_code": "563092a536194a1493551a0043f1f1a3", "icon": "Setting", "name": "平台设置", "sort": 10, "type": 1, "web_path": "/systemConfig", "component_name": "systemConfig"},
            {"code": "205910763e0e42fbbc12833d2f7d61bb", "parent_code": "563092a536194a1493551a0043f1f1a3", "icon": "Reading", "name": "数据字典", "sort": 20, "type": 1, "web_path": "/sysDictionary", "component_name": "sysDictionary"},
            {"code": "4f947108c5bf44f2b97e4a80daebf772", "parent_code": "563092a536194a1493551a0043f1f1a3", "icon": "Bell", "name": "通知公告", "sort": 30, "type": 1, "web_path": "/messagNotice", "component_name": "messagNotice"},
        ]

        # Only remove the three known demo entries from the original template.
        # The rest of the repository's custom/operational menu data is preserved.
        legacy_demo_codes = (
            "01599f73f61848aa811f687b1cfc1588",  # 功能演示
            "150e0957200146b3bd0226c45e8031f7",  # iframe嵌套
            "9ece0330c65e40df8da00190107d908e",  # 外链测试
        )
        Menu.objects.filter(code__in=legacy_demo_codes).delete()

        saved_menus = {}
        for item in menu_definitions:
            parent_code = item["parent_code"]
            parent = saved_menus.get(parent_code) if parent_code else None
            if parent_code and parent is None:
                raise RuntimeError(f"菜单父节点未初始化: {parent_code}")
            defaults = {
                "creator_id": "0",
                "parent": parent,
                "icon": item["icon"],
                "name": item["name"],
                "sort": item["sort"],
                "type": item["type"],
                "link_url": "",
                "web_path": item["web_path"],
                "component": "",
                "component_name": item["component_name"],
                "status": True,
                "isautopm": False,
                "cache": False,
                "visible": True,
            }
            obj, _ = Menu.objects.update_or_create(
                code=item["code"], defaults=defaults
            )
            saved_menus[item["code"]] = obj
        print(f"====================== end init menu ({len(saved_menus)} entries) ======================")

    def init_menu_button(self):
        print('====================== begin init menu button ======================')
        menu_button_data = [
            {
                "id": 1,
                "menu_id": "2e9937b37ac94e248e9ed159bfe7b655",
                "name": "查询",
                "value": "menuManage:Search",
                "api": "/api/system/menu/",
                "method": 0,
            },
            {
                "id": 2,
                "menu_id": "95227fe101e747908c12b56d2bae5e8e",
                "name": "新增",
                "value": "deptManage:Create",
                "api": "/api/system/dept/",
                "method": 1,
            },
            {
                "id": 3,
                "menu_id": "95227fe101e747908c12b56d2bae5e8e",
                "name": "删除",
                "value": "deptManage:Delete",
                "api": "/api/system/dept/{id}/",
                "method": 3,
            },
            {
                "id": 4,
                "menu_id": "95227fe101e747908c12b56d2bae5e8e",
                "name": "编辑",
                "value": "deptManage:Update",
                "api": "/api/system/dept/{id}/",
                "method": 2,
            },
            {
                "id": 5,
                "menu_id": "95227fe101e747908c12b56d2bae5e8e",
                "name": "查询",
                "value": "deptManage:Search",
                "api": "/api/system/dept/",
                "method": 0,
            },
            {
                "id": 7,
                "menu_id": "1b5018bdb5e04698b84da505e8a6b93c",
                "name": "新增",
                "value": "roleManage:Create",
                "api": "/api/system/role/",
                "method": 1,
            },
            {
                "id": 8,
                "menu_id": "1b5018bdb5e04698b84da505e8a6b93c",
                "name": "删除",
                "value": "roleManage:Delete",
                "api": "/api/system/role/{id}/",
                "method": 3,
            },
            {
                "id": 9,
                "menu_id": "1b5018bdb5e04698b84da505e8a6b93c",
                "name": "编辑",
                "value": "roleManage:Update",
                "api": "/api/system/role/{id}/",
                "method": 2,
            },
            {
                "id": 10,
                "menu_id": "1b5018bdb5e04698b84da505e8a6b93c",
                "name": "查询",
                "value": "roleManage:Search",
                "api": "/api/system/role/",
                "method": 0,
            },
            {
                "id": 12,
                "menu_id": "2e9937b37ac94e248e9ed159bfe7b655",
                "name": "删除",
                "value": "menuManage:Delete",
                "api": "/api/system/menu/{id}/",
                "method": 3,
            },
            {
                "id": 13,
                "menu_id": "2e9937b37ac94e248e9ed159bfe7b655",
                "name": "新增",
                "value": "menuManage:Create",
                "api": "/api/system/menu/",
                "method": 1,
            },
            {
                "id": 14,
                "menu_id": "2e9937b37ac94e248e9ed159bfe7b655",
                "name": "编辑",
                "value": "menuManage:Update",
                "api": "/api/system/menu/{id}/",
                "method": 2,
            },
            {
                "id": 15,
                "menu_id": "2e9937b37ac94e248e9ed159bfe7b655",
                "name": "移动",
                "value": "menuManage:Move",
                "api": "/api/system/menu/update_sort/",
                "method": 1,
            },
            {
                "id": 16,
                "menu_id": "95227fe101e747908c12b56d2bae5e8e",
                "name": "导出",
                "value": "deptManage:Export",
                "api": "/api/system/dept/export_data/",
                "method": 1,
            },
            {
                "id": 17,
                "menu_id": "95227fe101e747908c12b56d2bae5e8e",
                "name": "设置状态",
                "value": "deptManage:SetStatus",
                "api": "/api/system/dept/set_status/",
                "method": 1,
            },
            {
                "id": 18,
                "menu_id": "95227fe101e747908c12b56d2bae5e8e",
                "name": "导入",
                "value": "deptManage:Import",
                "api": "/api/system/dept/import_data/",
                "method": 1,
            },
            {
                "id": 19,
                "menu_id": "1b5018bdb5e04698b84da505e8a6b93c",
                "name": "设置状态",
                "value": "roleManage:SetStatus",
                "api": "/api/system/role/set_status/",
                "method": 1,
            },
            {
                "id": 20,
                "menu_id": "8faec98030e443b99ce0d4c636163db7",
                "name": "查询",
                "value": "authorityManage:Search",
                "api": "/api/system/role_permission/",
                "method": 0,
            },
            {
                "id": 21,
                "menu_id": "8faec98030e443b99ce0d4c636163db7",
                "name": "保存",
                "value": "authorityManage:Save",
                "api": "/api/system/role_permission/save_permission/",
                "method": 1,
            },
            {
                "id": 22,
                "menu_id": "31552696153b42599ce1faf6fe495824",
                "name": "新增",
                "value": "buserManage:Create",
                "api": "/api/system/user/",
                "method": 1,
            },
            {
                "id": 23,
                "menu_id": "31552696153b42599ce1faf6fe495824",
                "name": "删除",
                "value": "buserManage:Delete",
                "api": "/api/system/user/{id}/",
                "method": 3,
            },
            {
                "id": 24,
                "menu_id": "31552696153b42599ce1faf6fe495824",
                "name": "编辑",
                "value": "buserManage:Update",
                "api": "/api/system/user/{id}/",
                "method": 2,
            },
            {
                "id": 25,
                "menu_id": "31552696153b42599ce1faf6fe495824",
                "name": "查询",
                "value": "buserManage:Search",
                "api": "/api/system/user/",
                "method": 0,
            },
            {
                "id": 27,
                "menu_id": "31552696153b42599ce1faf6fe495824",
                "name": "导出",
                "value": "buserManage:Export",
                "api": "/api/system/user/export_data/",
                "method": 1,
            },
            {
                "id": 28,
                "menu_id": "31552696153b42599ce1faf6fe495824",
                "name": "导入",
                "value": "buserManage:Import",
                "api": "/api/system/user/import_data/",
                "method": 1,
            },
            {
                "id": 29,
                "menu_id": "31552696153b42599ce1faf6fe495824",
                "name": "设置状态",
                "value": "buserManage:SetStatus",
                "api": "/api/system/user/set_status/",
                "method": 1,
            },
            {
                "id": 30,
                "menu_id": "31552696153b42599ce1faf6fe495824",
                "name": "重置密码",
                "value": "buserManage:ResetPass",
                "api": "/api/system/user/reset_password/",
                "method": 2,
            },
            {
                "id": 31,
                "menu_id": "2e9937b37ac94e248e9ed159bfe7b655",
                "name": "按钮查看",
                "value": "menuManage:ButtonSearch",
                "api": "/api/system/button/",
                "method": 0,
            },
            {
                "id": 32,
                "menu_id": "2e9937b37ac94e248e9ed159bfe7b655",
                "name": "按钮增",
                "value": "menuManage:ButtonCreate",
                "api": "/api/system/button/",
                "method": 1,
            },
            {
                "id": 33,
                "menu_id": "2e9937b37ac94e248e9ed159bfe7b655",
                "name": "按钮改",
                "value": "menuManage:ButtonUpdate",
                "api": "/api/system/button/{id}/",
                "method": 2,
            },
            {
                "id": 34,
                "menu_id": "2e9937b37ac94e248e9ed159bfe7b655",
                "name": "按钮删",
                "value": "menuManage:ButtonDelete",
                "api": "/api/system/button/{id}/",
                "method": 3,
            },
            {
                "id": 35,
                "menu_id": "2e9937b37ac94e248e9ed159bfe7b655",
                "name": "按钮权查",
                "value": "menuManage:MenuButtonSearch",
                "api": "/api/system/menu_button/",
                "method": 0,
            },
            {
                "id": 36,
                "menu_id": "2e9937b37ac94e248e9ed159bfe7b655",
                "name": "按钮权增",
                "value": "menuManage:MenuButtonCreate",
                "api": "/api/system/menu_button/",
                "method": 1,
            },
            {
                "id": 37,
                "menu_id": "2e9937b37ac94e248e9ed159bfe7b655",
                "name": "按钮权改",
                "value": "menuManage:MenuButtonUpdate",
                "api": "/api/system/menu_button/{id}/",
                "method": 2,
            },
            {
                "id": 38,
                "menu_id": "2e9937b37ac94e248e9ed159bfe7b655",
                "name": "按钮权删",
                "value": "menuManage:MenuButtonDelete",
                "api": "/api/system/menu_button/{id}/",
                "method": 3,
            },
            {
                "id": 39,
                "menu_id": "2e9937b37ac94e248e9ed159bfe7b655",
                "name": "列权查看",
                "value": "menuManage:MenuFieldSearch",
                "api": "/api/system/menu_field/",
                "method": 0,
            },
            {
                "id": 40,
                "menu_id": "2e9937b37ac94e248e9ed159bfe7b655",
                "name": "列权新增",
                "value": "menuManage:MenuFieldCreate",
                "api": "/api/system/menu_field/",
                "method": 1,
            },
            {
                "id": 41,
                "menu_id": "2e9937b37ac94e248e9ed159bfe7b655",
                "name": "列权编辑",
                "value": "menuManage:MenuFieldUpdate",
                "api": "/api/system/menu_field/{id}/",
                "method": 2,
            },
            {
                "id": 42,
                "menu_id": "2e9937b37ac94e248e9ed159bfe7b655",
                "name": "列权删除",
                "value": "menuManage:MenuFieldDelete",
                "api": "/api/system/menu_field/{id}/",
                "method": 3,
            },
            {
                "id": 43,
                "menu_id": "2e9937b37ac94e248e9ed159bfe7b655",
                "name": "列权批量",
                "value": "menuManage:MenuFieldPL",
                "api": "/api/system/menu_field/auto_create/",
                "method": 1,
            },
            {
                "id": 44,
                "menu_id": "2e9937b37ac94e248e9ed159bfe7b655",
                "name": "按钮权批",
                "value": "menuManage:MenuButtonPL",
                "api": "/api/system/menu_button/auto_create/",
                "method": 1,
            },
            {
                "id": 45,
                "menu_id": "8faec98030e443b99ce0d4c636163db7",
                "name": "菜单",
                "value": "authorityManage:MenuSearch",
                "api": "/api/system/role_id_to_menu/{id}/",
                "method": 0,
            },
            {
                "id": 47,
                "menu_id": "98870fbaffb348ab9fd16a88e946bf09",
                "name": "查询",
                "value": "PersonalCenter:Search",
                "api": "/api/system/user/user_info/",
                "method": 0,
            },
            {
                "id": 48,
                "menu_id": "98870fbaffb348ab9fd16a88e946bf09",
                "name": "重置密码",
                "value": "PersonalCenter:ResetPass",
                "api": "/api/system/user/change_password/",
                "method": 1,
            },
            {
                "id": 49,
                "menu_id": "98870fbaffb348ab9fd16a88e946bf09",
                "name": "编辑",
                "value": "PersonalCenter:Update",
                "api": "/api/system/user/user_info/",
                "method": 2,
            },
            {
                "id": 50,
                "menu_id": "98870fbaffb348ab9fd16a88e946bf09",
                "name": "修改头像",
                "value": "PersonalCenter:UpdateAvatar",
                "api": "/api/system/user/change_avatar/",
                "method": 1,
            },
            {
                "id": 51,
                "menu_id": "24d2eb79a21141afbe73058cc02545e0",
                "name": "查询",
                "value": "journalManage:Search",
                "api": "/api/system/operation_log/",
                "method": 0,
            },
            {
                "id": 52,
                "menu_id": "24d2eb79a21141afbe73058cc02545e0",
                "name": "删除",
                "value": "journalManage:Delete",
                "api": "/api/system/operation_log/{id}/",
                "method": 3,
            },
            {
                "id": 53,
                "menu_id": "24d2eb79a21141afbe73058cc02545e0",
                "name": "全部清除",
                "value": "journalManage:DeleteAll",
                "api": "/api/system/operation_log/deletealllogs/",
                "method": 3,
            },
            {
                "id": 54,
                "menu_id": "98870fbaffb348ab9fd16a88e946bf09",
                "name": "日志查询",
                "value": "PersonalCenter:GetOPLog",
                "api": "/api/system/operation_log/getOwnerLogs/",
                "method": 0,
            },
            {
                "id": 55,
                "menu_id": "205910763e0e42fbbc12833d2f7d61bb",
                "name": "查询",
                "value": "sysDictionary:Search",
                "api": "/api/system/dictionary/",
                "method": 0,
            },
            {
                "id": 56,
                "menu_id": "205910763e0e42fbbc12833d2f7d61bb",
                "name": "新增",
                "value": "sysDictionary:Create",
                "api": "/api/system/dictionary/",
                "method": 1,
            },
            {
                "id": 57,
                "menu_id": "205910763e0e42fbbc12833d2f7d61bb",
                "name": "删除",
                "value": "sysDictionary:Delete",
                "api": "/api/system/dictionary/{id}/",
                "method": 3,
            },
            {
                "id": 58,
                "menu_id": "205910763e0e42fbbc12833d2f7d61bb",
                "name": "编辑",
                "value": "sysDictionary:Update",
                "api": "/api/system/dictionary/{id}/",
                "method": 2,
            },
            {
                "id": 59,
                "menu_id": "205910763e0e42fbbc12833d2f7d61bb",
                "name": "设置状态",
                "value": "sysDictionary:SetStatus",
                "api": "/api/system/dictionary/set_status/",
                "method": 1,
            },
            {
                "id": 60,
                "menu_id": "a8b435647f0b4a3f852ec796433e8919",
                "name": "查询",
                "value": "loginLogs:Search",
                "api": "/api/system/login_log/",
                "method": 0,
            },
            {
                "id": 61,
                "menu_id": "a8b435647f0b4a3f852ec796433e8919",
                "name": "删除",
                "value": "loginLogs:Delete",
                "api": "/api/system/login_log/{id}/",
                "method": 3,
            },
            {
                "id": 62,
                "menu_id": "a8b435647f0b4a3f852ec796433e8919",
                "name": "全部清除",
                "value": "loginLogs:DeleteAll",
                "api": "/api/system/login_log/deletealllogs/",
                "method": 3,
            },
            {
                "id": 63,
                "menu_id": "98870fbaffb348ab9fd16a88e946bf09",
                "name": "登录日志",
                "value": "PersonalCenter:GetLoginLog",
                "api": "/api/system/login_log/getOwnerLogs/",
                "method": 0,
            },
            {
                "id": 64,
                "menu_id": "6354ba32ae734b5eaa799a65f76deee6",
                "name": "新增分组",
                "value": "systemConfig:CreateGroup",
                "api": "/api/system/sysconfig/",
                "method": 1,
            },
            {
                "id": 65,
                "menu_id": "6354ba32ae734b5eaa799a65f76deee6",
                "name": "新增项",
                "value": "systemConfig:CreateContent",
                "api": "/api/system/sysconfig/",
                "method": 1,
            },
            {
                "id": 66,
                "menu_id": "6354ba32ae734b5eaa799a65f76deee6",
                "name": "保存",
                "value": "systemConfig:Save",
                "api": "/api/system/sysconfig/{id}/",
                "method": 2,
            },
            {
                "id": 67,
                "menu_id": "6354ba32ae734b5eaa799a65f76deee6",
                "name": "查询",
                "value": "systemConfig:Search",
                "api": "/api/system/sysconfig/",
                "method": 0,
            },
            {
                "id": 68,
                "menu_id": "6354ba32ae734b5eaa799a65f76deee6",
                "name": "删除",
                "value": "systemConfig:Delete",
                "api": "/api/system/sysconfig/{id}/",
                "method": 3,
            },
            {
                "id": 69,
                "menu_id": "6354ba32ae734b5eaa799a65f76deee6",
                "name": "编辑",
                "value": "systemConfig:Update",
                "api": "/api/system/sysconfig/{id}/",
                "method": 2,
            },
            {
                "id": 70,
                "menu_id": "4f947108c5bf44f2b97e4a80daebf772",
                "name": "查询",
                "value": "messagNotice:Search",
                "api": "/api/system/msg/",
                "method": 0,
            },
            {
                "id": 71,
                "menu_id": "4f947108c5bf44f2b97e4a80daebf772",
                "name": "新增",
                "value": "messagNotice:Create",
                "api": "/api/system/msg/",
                "method": 1,
            },
            {
                "id": 72,
                "menu_id": "4f947108c5bf44f2b97e4a80daebf772",
                "name": "删除",
                "value": "messagNotice:Delete",
                "api": "/api/system/msg/{id}/",
                "method": 3,
            },
            {
                "id": 73,
                "menu_id": "98870fbaffb348ab9fd16a88e946bf09",
                "name": "消息查询",
                "value": "PersonalCenter:PMsg",
                "api": "/api/system/msg/ownmsg/",
                "method": 0,
            },
            {
                "id": 74,
                "menu_id": "4f947108c5bf44f2b97e4a80daebf772",
                "name": "编辑",
                "value": "messagNotice:Update",
                "api": "/api/system/msg/{id}/",
                "method": 2,
            },
            {
                "id": 75,
                "menu_id": "44662b7fe6b54395994f28ed88eaf3f0",
                "name": "查询",
                "value": "myMessage:Search",
                "api": "/api/system/msg/ownmsg/",
                "method": 0,
            },
            {
                "id": 76,
                "menu_id": "44662b7fe6b54395994f28ed88eaf3f0",
                "name": "删除",
                "value": "myMessage:Delete",
                "api": "/api/system/msg/delownmsg/",
                "method": 1,
            },
            {
                "id": 77,
                "menu_id": "44662b7fe6b54395994f28ed88eaf3f0",
                "name": "详情",
                "value": "myMessage:Detail",
                "api": "/api/system/msg/readownmsg/",
                "method": 1,
            },
        ]
        menu_dict = {it.code: it for it in Menu.objects.all()}
        for it in menu_button_data:
            it.pop("id")
            it['menu_id'] =  menu_dict[it['menu_id']].id
            MenuButton.objects.update_or_create(
                menu_id=it['menu_id'],
                name=it['name'],
                defaults=it,
            )
        print('====================== end init menu button ======================')

    def init_role(self):
        """初始化角色表"""
        print('====================== begin init role ======================')
        Role.objects.update_or_create(
            key="admin",
            defaults={
                "name": "管理员",
                "key": "admin",
                "sort": 1,
                "status": 1,
            }
        )
        print('====================== end init role ======================')


    def init_users(self):
        """只创建一个超级管理员，不创建演示用户或使用固定密码。

        对已存在用户不修改密码和角色，避免重跑初始化时重置账户。
        可通过 INITIAL_SUPERUSER_PASSWORD 设定首次密码；未设定时
        用户不可用密码登录，管理员需运行 manage.py changepassword SuperAdmin。
        """
        print("====================== begin init user ======================")
        if Users.objects.filter(username="SuperAdmin").exists():
            print("SuperAdmin 已存在，跳过账号和密码变更")
            return

        password = os.environ.get("INITIAL_SUPERUSER_PASSWORD")
        if password:
            from django.contrib.auth.password_validation import validate_password
            validate_password(password)

        user = Users(
            username="SuperAdmin",
            name="超级管理员",
            nickname="超级管理员",
            identity=0,
            is_superuser=True,
            is_staff=True,
            is_active=True,
        )
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        if not password:
            print("未配置 INITIAL_SUPERUSER_PASSWORD，请执行 python manage.py changepassword SuperAdmin 设置初始密码")
        print("====================== end init user ======================")


    def init_systemconfig(self):
        print('====================== init system config ======================')
        do_insert = True
        if self.delete:
            SystemConfig.objects.filter(parent__isnull=False).delete()
            SystemConfig.objects.filter(parent__isnull=True).delete()
        else:
            if SystemConfig.objects.all().count() == 0:
                print('system config already initialized, because SystemConfig any data exist!')
                do_insert = False

        if do_insert:
            data = [
                {
                    "creator_id": "0",
                    "title": "基础配置",
                    "key": "base",
                    "value": None,
                    "sort": 0,
                    "status": True,
                    "data_options": None,
                    "form_item_type": 0,
                    "rule": None,
                    "placeholder": None,
                    "tip": None,
                    "setting": None,
                    "childrens": [
                        {
                            "creator_id": "0",
                            "title": "logo",
                            "key": "logo",
                            "value": "",
                            "sort": 10,
                            "status": True,
                            "data_options": None,
                            "form_item_type": 7,
                            "rule": None,
                            "placeholder": None,
                            "tip": None,
                            "setting": None,
                        },
                        {
                            "creator_id": "0",
                            "title": "登录验证码",
                            "key": "loginCaptcha",
                            "value": "true",
                            "sort": 8,
                            "status": True,
                            "data_options": None,
                            "form_item_type": 9,
                            "rule": None,
                            "placeholder": None,
                            "tip": "登录验证码开启/关闭",
                            "setting": None,
                        },
                        {
                            "creator_id": "0",
                            "title": "系统标题",
                            "key": "systitle",
                            "value": "Enterprise Agent Hub",
                            "sort": 5,
                            "status": True,
                            "data_options": None,
                            "form_item_type": 0,
                            "rule": None,
                            "placeholder": "请输入系统标题",
                            "tip": None,
                            "setting": None,
                        },
                    ],
                },
                {
                    "creator_id": "0",
                    "parent_id": None,
                    "title": "Api白名单",
                    "key": "apiWhiteList",
                    "value": "[]",
                    "sort": 0,
                    "status": True,
                    "data_options": None,
                    "form_item_type": 0,
                    "rule": None,
                    "placeholder": None,
                    "tip": None,
                    "setting": None,
                },
            ]
            for it in data:
                childrens = it.pop("childrens", []) or []
                (obj, status) = SystemConfig.objects.update_or_create(key=it["key"], defaults=it)
                for cit in childrens:
                    cit['parent'] = obj
                    (child_obj, status) = SystemConfig.objects.update_or_create(key=cit["key"], parent_id=obj.id, defaults=cit)
        print('init system config count:', len(data))


        print('====================== end system config ======================')

    def init_dictionary(self):
        print('====================== begin init dictionary ======================')
        do_insert = True
        if self.delete:
            for it in Dictionary.objects.filter(parent__isnull=True):
                it.recursion_delete()
        else:
            if Dictionary.objects.count() > 0:
                print('init dictionary zero because Dictionary any data exist!')
                do_insert = False
        if do_insert:
            data = [
                    {
                        "creator_id": "0",
                        "label": "是/否-布尔值",
                        "value": "button_bool",
                        "status": True,
                        "sort": 29,
                        "parent_id": None,
                        "remark": "",
                        "childrens": [
                            {
                                "creator_id": "0",
                                "label": "是",
                                "value": "true",
                                "status": True,
                                "sort": 1,
                                "remark": "",
                            },
                            {
                                "creator_id": "0",
                                "label": "否",
                                "value": "false",
                                "status": True,
                                "sort": 2,
                                "remark": "",
                            },
                        ]
                    },

                    {
                        "creator_id": "0",
                        "label": "是/否-数字值",
                        "value": "button_number",
                        "status": True,
                        "sort": 30,
                        "parent_id": None,
                        "remark": "",
                        "childrens": [
                            {
                                "creator_id": "0",
                                "label": "否",
                                "value": "0",
                                "status": True,
                                "sort": 2,
                                "remark": "",
                            },
                            {
                                "creator_id": "0",
                                "label": "是",
                                "value": "1",
                                "status": True,
                                "sort": 1,
                                "remark": "",
                            },
                        ]
                    },

                    {
                        "creator_id": "0",
                        "label": "性别",
                        "value": "gender",
                        "status": True,
                        "sort": 1,
                        "parent_id": None,
                        "remark": "",
                        "childrens": [
                            {
                                "creator_id": "0",
                                "label": "女",
                                "value": "1",
                                "status": True,
                                "sort": 2,
                                "remark": "",
                            },
                            {
                                "creator_id": "0",
                                "label": "未知",
                                "value": "0",
                                "status": True,
                                "sort": 1,
                                "remark": "",
                            },
                            {
                                "creator_id": "0",
                                "label": "男",
                                "value": "2",
                                "status": True,
                                "sort": 3,
                                "remark": "",
                            },
                        ],
                    },
        ]
            for it in data:
                childrens = it.pop("childrens", []) or []
                (obj, status) = Dictionary.objects.update_or_create(label=it["label"], defaults=it)
                for cit in childrens:
                    cit['parent'] = obj
                    (child_obj, status) = Dictionary.objects.update_or_create(label=cit["label"], parent_id=obj.id, defaults=cit)
            print('success init dictionary count:', len(data))

        print('====================== end init dictionary ======================')



    def run(self):
        """执行初始化；任何错误都中断事务并回滚。"""
        self.init_button()
        self.init_menu()
        self.init_menu_button()
        self.init_dept()
        self.init_role()
        self.init_users()
        self.init_systemconfig()
        self.init_dictionary()
        print("所有初始化完成!")


def main(is_delete=False):
    """主函数"""
    with transaction.atomic():
        Initialize(is_delete).run()


if __name__ == "__main__":
    main()
