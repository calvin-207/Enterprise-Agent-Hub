"""Built-in reference pricing for well-known models (USD per 1M tokens).

Vendor /v1/models endpoints return model IDs only — no standard pricing API
exists. This table auto-fills *estimation* prices when sync CREATES a new
ModelProfile. It never overwrites existing records, and admins are expected
to verify against vendor price pages; values are dated snapshots (2026-11)
that will drift over time. A 0 price still means "not configured".
"""

# Exact model_code matches. Prices use vendor peak-hour USD rates (conservative).
_EXACT = {
    # DeepSeek (official pricing page, fetched 2026-11-19; peak rates)
    "deepseek-flash": {"name": "DeepSeek Flash (V4.1)", "input": "0.30", "output": "1.20", "max_output_tokens": 16384},
    "deepseek-v4-pro": {"name": "DeepSeek V4 Pro", "input": "1.32", "output": "3.96", "max_output_tokens": 16384},
    # DeepSeek legacy names (retired but still accepted by some gateways)
    "deepseek-chat": {"name": "DeepSeek Chat (legacy)", "input": "0.27", "output": "1.10", "max_output_tokens": 8192},
    "deepseek-reasoner": {"name": "DeepSeek Reasoner (legacy)", "input": "0.55", "output": "2.19", "max_output_tokens": 8192},
    # OpenAI
    "gpt-4o": {"name": "GPT-4o", "input": "2.50", "output": "10.00", "max_output_tokens": 16384},
    "gpt-4o-mini": {"name": "GPT-4o mini", "input": "0.15", "output": "0.60", "max_output_tokens": 16384},
    "gpt-4.1": {"name": "GPT-4.1", "input": "2.00", "output": "8.00", "max_output_tokens": 16384},
    "gpt-4.1-mini": {"name": "GPT-4.1 mini", "input": "0.40", "output": "1.60", "max_output_tokens": 16384},
    "gpt-4.1-nano": {"name": "GPT-4.1 nano", "input": "0.10", "output": "0.40", "max_output_tokens": 16384},
    "o3": {"name": "o3", "input": "2.00", "output": "8.00", "max_output_tokens": 16384},
    "o4-mini": {"name": "o4-mini", "input": "1.10", "output": "4.40", "max_output_tokens": 16384},
    # Anthropic (OpenAI-compatible layer)
    "claude-opus-4-1": {"name": "Claude Opus 4.1", "input": "15.00", "output": "75.00", "max_output_tokens": 16384},
    "claude-sonnet-4-5": {"name": "Claude Sonnet 4.5", "input": "3.00", "output": "15.00", "max_output_tokens": 16384},
    "claude-3-7-sonnet-latest": {"name": "Claude 3.7 Sonnet", "input": "3.00", "output": "15.00", "max_output_tokens": 16384},
    "claude-3-5-haiku-latest": {"name": "Claude 3.5 Haiku", "input": "0.80", "output": "4.00", "max_output_tokens": 8192},
    # Google Gemini (OpenAI-compatible layer)
    "gemini-2.5-pro": {"name": "Gemini 2.5 Pro", "input": "1.25", "output": "10.00", "max_output_tokens": 16384},
    "gemini-2.5-flash": {"name": "Gemini 2.5 Flash", "input": "0.30", "output": "2.50", "max_output_tokens": 8192},
    "gemini-2.0-flash": {"name": "Gemini 2.0 Flash", "input": "0.10", "output": "0.40", "max_output_tokens": 8192},
}

# Prefix matches for dated/variant model IDs (e.g. gpt-4o-2024-08-06,
# qwen-plus-2025-xx). Order matters: more specific prefixes first.
_PREFIXES = [
    ("deepseek-v4-flash", {"name": "DeepSeek Flash (V4.1)", "input": "0.30", "output": "1.20", "max_output_tokens": 16384}),
    ("claude-opus-4", {"name": "Claude Opus 4.x", "input": "15.00", "output": "75.00", "max_output_tokens": 16384}),
    ("claude-sonnet-4", {"name": "Claude Sonnet 4.x", "input": "3.00", "output": "15.00", "max_output_tokens": 16384}),
    ("claude-3-7-sonnet", {"name": "Claude 3.7 Sonnet", "input": "3.00", "output": "15.00", "max_output_tokens": 16384}),
    ("claude-3-5-sonnet", {"name": "Claude 3.5 Sonnet", "input": "3.00", "output": "15.00", "max_output_tokens": 8192}),
    ("claude-3-5-haiku", {"name": "Claude 3.5 Haiku", "input": "0.80", "output": "4.00", "max_output_tokens": 8192}),
    ("gpt-4o-mini", {"name": "GPT-4o mini", "input": "0.15", "output": "0.60", "max_output_tokens": 16384}),
    ("gpt-4o", {"name": "GPT-4o", "input": "2.50", "output": "10.00", "max_output_tokens": 16384}),
    ("o4-mini", {"name": "o4-mini", "input": "1.10", "output": "4.40", "max_output_tokens": 16384}),
    ("gemini-2.5-pro", {"name": "Gemini 2.5 Pro", "input": "1.25", "output": "10.00", "max_output_tokens": 16384}),
    ("gemini-2.5-flash", {"name": "Gemini 2.5 Flash", "input": "0.30", "output": "2.50", "max_output_tokens": 8192}),
    # Moonshot Kimi (CNY list price ≈ converted)
    ("kimi-k2", {"name": "Kimi K2", "input": "0.55", "output": "2.20", "max_output_tokens": 16384}),
    ("kimi-latest", {"name": "Kimi Latest", "input": "0.83", "output": "3.32", "max_output_tokens": 16384}),
    ("moonshot-v1", {"name": "Moonshot v1", "input": "1.10", "output": "3.32", "max_output_tokens": 8192}),
    # Zhipu GLM (CNY list price ≈ converted)
    ("glm-4-flash", {"name": "GLM-4-Flash（免费）", "input": "0.00", "output": "0.00", "max_output_tokens": 4096}),
    ("glm-4-air", {"name": "GLM-4-Air", "input": "0.14", "output": "0.14", "max_output_tokens": 4096}),
    ("glm-4-plus", {"name": "GLM-4-Plus", "input": "0.70", "output": "0.70", "max_output_tokens": 4096}),
    # Alibaba Qwen (DashScope CNY list price ≈ converted)
    ("qwen-turbo", {"name": "Qwen Turbo", "input": "0.04", "output": "0.08", "max_output_tokens": 8192}),
    ("qwen-plus", {"name": "Qwen Plus", "input": "0.11", "output": "0.28", "max_output_tokens": 8192}),
    ("qwen-max", {"name": "Qwen Max", "input": "0.33", "output": "1.33", "max_output_tokens": 8192}),
]


def pricing_reference_for(model_code):
    """Return a reference entry for a synced model ID, or None if unknown."""
    if not isinstance(model_code, str):
        return None
    entry = _EXACT.get(model_code)
    if entry:
        return dict(entry)
    for prefix, entry in _PREFIXES:
        if model_code.startswith(prefix):
            return dict(entry)
    return None
