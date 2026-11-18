"""Public provider/model metadata only. Secrets are never stored in these models."""
from django.db import models


class ModelProvider(models.Model):
    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=120)
    adapter_type = models.CharField(max_length=40, default="openai_compatible")
    secret_ref = models.CharField(max_length=255, blank=True, default="")
    encrypted_api_key = models.TextField(blank=True, default="")
    base_url = models.URLField(max_length=255, blank=True, default="")
    last_sync_at = models.DateTimeField(null=True, blank=True)
    enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.code


class ModelProfile(models.Model):
    provider = models.ForeignKey(ModelProvider, on_delete=models.PROTECT, related_name="profiles")
    name = models.CharField(max_length=120)
    model_code = models.CharField(max_length=120)
    enabled = models.BooleanField(default=False)
    configuration = models.JSONField(default=dict, blank=True)
    input_price_per_million = models.DecimalField(max_digits=14, decimal_places=6, default=0)
    output_price_per_million = models.DecimalField(max_digits=14, decimal_places=6, default=0)
    max_output_tokens = models.PositiveIntegerField(default=1024)
    is_default = models.BooleanField(default=False)
    source = models.CharField(max_length=16, default="manual")
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("provider", "model_code"), name="eah_unique_provider_model"),
            models.UniqueConstraint(fields=("is_default",), condition=models.Q(is_default=True), name="eah_one_default_model"),
        ]

    def __str__(self):
        return f"{self.provider.code}/{self.model_code}"
