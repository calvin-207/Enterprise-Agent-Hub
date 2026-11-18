"""Public provider/model metadata only. Secrets are never stored in these models."""
from django.db import models


class ModelProvider(models.Model):
    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=120)
    adapter_type = models.CharField(max_length=40, default="openai_compatible")
    secret_ref = models.CharField(max_length=255, blank=True, default="")
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("provider", "model_code"), name="eah_unique_provider_model"),
        ]

    def __str__(self):
        return f"{self.provider.code}/{self.model_code}"
