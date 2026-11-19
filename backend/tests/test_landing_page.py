"""
官网 SEO 落地页路由测试

覆盖：
- 根路径 / 返回静态 SEO 落地页（含标题、描述与登录入口 /app/#/login）
- /app/ 与 /app 均返回管理控制台 SPA 入口（hash 路由登录页保留）
- robots.txt / sitemap.xml 可访问且返回正确 Content-Type

说明：相关页面为前端构建产物（backend/frontend/leeadmin/，已 gitignore），
需先在 frontend/ 目录执行 `npm run build:backend` 生成；未构建时测试自动跳过，
与线上集成部署行为一致。
"""
import os

import pytest
from django.conf import settings
from django.test import Client

LEEADMIN_DIR = os.path.join(settings.FRONTEND_ROOT, "leeadmin")


def _has_template(filename: str) -> bool:
    return os.path.exists(os.path.join(LEEADMIN_DIR, filename))


@pytest.fixture
def page_client():
    return Client()


@pytest.mark.skipif(
    not _has_template("index.html"),
    reason="前端构建产物 leeadmin/index.html 不存在，请先在 frontend/ 执行 npm run build:backend",
)
class TestSeoLandingPage:
    """根路径渲染静态 SEO 落地页"""

    def test_root_returns_landing_with_seo_meta(self, page_client):
        resp = page_client.get("/")
        assert resp.status_code == 200
        html = resp.content.decode("utf-8")

        # SEO 基础要素
        assert '<html lang="zh-CN">' in html
        assert "<title>Enterprise Agent Hub" in html
        assert 'name="description"' in html
        assert 'name="robots"' in html
        assert "application/ld+json" in html  # 结构化数据

        # 登录/注册入口直达控制台
        assert "/app/#/login" in html
        assert "立即登录" in html

    def test_landing_needs_no_javascript_to_show_login(self, page_client):
        """落地页为纯静态 HTML，登录入口是可抓取的 <a> 链接而非 JS 渲染"""
        resp = page_client.get("/")
        html = resp.content.decode("utf-8")
        assert '<a class="btn btn-primary js-open-login" href="/app/#/login"' in html

    def test_landing_has_inline_login_modal(self, page_client):
        """落地页内置登录弹窗：直接调用 /api/token/，无需跳转到登录页"""
        resp = page_client.get("/")
        html = resp.content.decode("utf-8")
        assert 'id="loginModal"' in html
        assert 'id="loginForm"' in html
        assert "/api/token/" in html
        # 验证码开关按系统配置探测（loginCaptcha）
        assert "/api/system/getconfig/" in html


@pytest.mark.skipif(
    not _has_template("app.html"),
    reason="前端构建产物 leeadmin/app.html 不存在，请先在 frontend/ 执行 npm run build:backend",
)
class TestConsoleEntry:
    """管理控制台 SPA 入口迁移至 /app/（原登录页 hash 路由保留）"""

    @pytest.mark.parametrize("path", ["/app/", "/app"])
    def test_app_entry_serves_spa_shell(self, page_client, path):
        resp = page_client.get(path)
        assert resp.status_code == 200
        html = resp.content.decode("utf-8")
        # SPA 挂载点与应用入口脚本
        assert 'id="app"' in html
        # 控制台空壳无需搜索引擎收录
        assert 'name="robots" content="noindex' in html


@pytest.mark.skipif(
    not (_has_template("robots.txt") and _has_template("sitemap.xml")),
    reason="前端构建产物 leeadmin/robots.txt 或 sitemap.xml 不存在，请先在 frontend/ 执行 npm run build:backend",
)
class TestSeoFiles:
    """SEO 基础文件路由"""

    def test_robots_txt(self, page_client):
        resp = page_client.get("/robots.txt")
        assert resp.status_code == 200
        assert resp["Content-Type"].startswith("text/plain")
        body = resp.content.decode("utf-8")
        assert "User-agent: *" in body
        assert "Disallow: /app" in body

    def test_sitemap_xml(self, page_client):
        resp = page_client.get("/sitemap.xml")
        assert resp.status_code == 200
        assert resp["Content-Type"].startswith("application/xml")
        body = resp.content.decode("utf-8")
        assert "<urlset" in body
        assert "<loc>" in body
