"""Usage accounting with explicit unknown-usage semantics and immutable price snapshots."""
from decimal import Decimal, ROUND_HALF_UP
from agent_runtime.models import ModelUsage


def save_usage(run, version, usage):
    profile = version.model_profile
    value = usage if isinstance(usage, dict) else {}
    def count(key):
        n = value.get(key)
        return n if type(n) is int and 0 <= n <= 10**9 else None

    input_tokens, output_tokens = count("input_tokens"), count("output_tokens")
    estimated_cost = None
    if input_tokens is not None and output_tokens is not None:
        cost = (
            Decimal(input_tokens) * profile.input_price_per_million
            + Decimal(output_tokens) * profile.output_price_per_million
        ) / Decimal(1000000)
        estimated_cost = cost.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
    return ModelUsage.objects.update_or_create(
        run=run,
        defaults={
            "provider_code": profile.provider.code,
            "model_code": profile.model_code,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "estimated_cost": estimated_cost,
            "input_price_per_million": profile.input_price_per_million,
            "output_price_per_million": profile.output_price_per_million,
        },
    )[0]
