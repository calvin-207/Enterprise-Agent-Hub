"""Only registered read-only tools are publishable in P1-A."""
from django.db import models


class ToolDefinition(models.Model):
    class Kind(models.TextChoices):
        MOCK_READ = "mock_read", "模拟只读工具"

    code = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=24, choices=Kind.choices, default=Kind.MOCK_READ)
    version = models.PositiveIntegerField(default=1)
    input_schema = models.JSONField(default=dict)
    output_schema = models.JSONField(default=dict)
    enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.code
