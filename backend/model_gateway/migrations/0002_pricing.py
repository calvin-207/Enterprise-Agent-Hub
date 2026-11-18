from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("model_gateway", "0001_initial")]
    operations = [
        migrations.AddField("modelprofile", "input_price_per_million", models.DecimalField(decimal_places=6, default=0, max_digits=14)),
        migrations.AddField("modelprofile", "output_price_per_million", models.DecimalField(decimal_places=6, default=0, max_digits=14)),
        migrations.AddField("modelprofile", "max_output_tokens", models.PositiveIntegerField(default=1024)),
    ]
