from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="ToolDefinition",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(max_length=100, unique=True)),
                ("name", models.CharField(max_length=120)),
                ("kind", models.CharField(choices=[("mock_read", "模拟只读工具")], default="mock_read", max_length=24)),
                ("version", models.PositiveIntegerField(default=1)),
                ("input_schema", models.JSONField(default=dict)),
                ("output_schema", models.JSONField(default=dict)),
                ("enabled", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
