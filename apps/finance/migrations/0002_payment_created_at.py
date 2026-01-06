from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="created_at",
            field=models.DateTimeField(default=timezone.now, editable=False),
            preserve_default=False,
        ),
    ]
