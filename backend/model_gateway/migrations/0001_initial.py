from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="ModelProvider",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(max_length=64, unique=True)),
                ("name", models.CharField(max_length=120)),
                ("adapter_type", models.CharField(default="openai_compatible", max_length=40)),
                ("secret_ref", models.CharField(blank=True, default="", max_length=255)),
                ("enabled", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="ModelProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("model_code", models.CharField(max_length=120)),
                ("enabled", models.BooleanField(default=False)),
                ("configuration", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("provider", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="profiles", to="model_gateway.modelprovider")),
            ],
        ),
        migrations.AddConstraint(
            model_name="modelprofile",
            constraint=models.UniqueConstraint(fields=("provider", "model_code"), name="eah_unique_provider_model"),
        ),
    ]
