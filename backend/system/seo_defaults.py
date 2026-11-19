# -*- coding: utf-8 -*-
"""
官网 SEO 落地页默认文案

- 后台「系统配置 → 官网 SEO」分组各配置项的种子默认值（system/initialize.py）
- 分组未配置/未初始化时，落地页视图（system/views/frontend.py）的兜底值

两处共用一份，保证初始化与兜底始终一致。
"""

SEO_LANDING_DEFAULTS = {
    "title": "Enterprise Agent Hub｜企业级 AI Agent 业务执行与治理平台",
    "description": (
        "Enterprise Agent Hub 将大模型 Agent 落地为企业可用的业务执行平台："
        "Agent 编排与会话、自动化任务调度、业务工具网关、RBAC 权限治理、"
        "实时进度推送与全链路审计，助力企业安全可控地自动化执行业务。"
    ),
    "keywords": (
        "Enterprise Agent Hub, AI Agent, 企业级 Agent 平台, Agent 编排, "
        "任务自动化, 业务工具网关, RBAC 权限治理, Django, Vue3, 大模型"
    ),
    "copyright": "© 2026 Enterprise Agent Hub · 企业级 AI Agent 业务执行与治理平台",
    "icp": "ICP备xxxxx-31",
}
