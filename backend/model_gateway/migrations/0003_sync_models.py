from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("model_gateway", "0002_pricing")]
    operations = [
        migrations.AddField("modelprovider", "encrypted_api_key", models.TextField(blank=True, default="")),
        migrations.AddField("modelprovider", "base_url", models.URLField(blank=True, default="", max_length=255)),
        migrations.AddField("modelprovider", "last_sync_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("modelprofile", "is_default", models.BooleanField(default=False)),
        migrations.AddField("modelprofile", "source", models.CharField(default="manual", max_length=16)),
        migrations.AddField("modelprofile", "last_seen_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddConstraint("modelprofile", models.UniqueConstraint(fields=("is_default",), condition=models.Q(is_default=True), name="eah_one_default_model")),
    ]
