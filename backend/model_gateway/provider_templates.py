"""Built-in provider templates for quick setup.

Static public metadata only (endpoints and doc links) — no secrets here.
Choosing a template merely pre-fills the admin form; API keys are always
entered (or env-referenced) separately by the administrator.
"""

PROVIDER_TEMPLATES = [
    {
        "code": "openai",
        "name": "OpenAI 官方",
        "adapter_type": "openai",
        "base_url": "",
        "docs_url": "https://platform.openai.com/docs",
        "note": "官方 API，无需 Base URL；Key 在 platform.openai.com 创建。",
    },
    {
        "code": "deepseek",
        "name": "DeepSeek",
        "adapter_type": "openai_compatible",
        "base_url": "https://api.deepseek.com/v1",
        "docs_url": "https://api-docs.deepseek.com",
        "note": "常见模型 deepseek-chat（V3）、deepseek-reasoner（R1）；/v1 仅为 OpenAI 兼容路径，与模型版本无关。",
    },
    {
        "code": "zhipu",
        "name": "智谱 GLM",
        "adapter_type": "openai_compatible",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "docs_url": "https://open.bigmodel.cn/docs",
        "note": "GLM-4 系列；API Key 在 open.bigmodel.cn 获取。",
    },
    {
        "code": "moonshot",
        "name": "Kimi（月之暗面）",
        "adapter_type": "openai_compatible",
        "base_url": "https://api.moonshot.cn/v1",
        "docs_url": "https://platform.moonshot.cn/docs",
        "note": "kimi-k2、moonshot-v1 系列；上下文长度按模型而定。",
    },
    {
        "code": "qwen",
        "name": "通义千问（阿里云百炼）",
        "adapter_type": "openai_compatible",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "docs_url": "https://help.aliyun.com/zh/model-studio/",
        "note": "qwen-max / qwen-plus / qwen-turbo / qwen3 系列；使用百炼 DashScope 的兼容模式入口。",
    },
    {
        "code": "gemini",
        "name": "Google Gemini",
        "adapter_type": "openai_compatible",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "docs_url": "https://ai.google.dev/gemini-api/docs/openai",
        "note": "使用 Google 官方 OpenAI 兼容层；部分地区网络可能无法直连。",
    },
    {
        "code": "anthropic",
        "name": "Anthropic Claude",
        "adapter_type": "openai_compatible",
        "base_url": "https://api.anthropic.com/v1",
        "docs_url": "https://docs.anthropic.com",
        "note": "使用 Anthropic 官方 OpenAI SDK 兼容层；部分地区网络可能无法直连。",
    },
]
