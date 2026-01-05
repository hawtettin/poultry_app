# Generated manually for initial deployment (Render)
from __future__ import annotations

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name="House",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True)),
                ("code", models.CharField(blank=True, default="", max_length=50)),
            ],
        ),
        migrations.CreateModel(
            name="Season",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True)),
                ("start_date", models.DateField()),
                ("end_date", models.DateField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
            ],
        ),
        migrations.CreateModel(
            name="Flock",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("start_date", models.DateField()),
                ("initial_count", models.PositiveIntegerField()),
                ("breed", models.CharField(blank=True, default="", max_length=120)),
                ("supplier", models.CharField(blank=True, default="", max_length=120)),
                ("notes", models.TextField(blank=True, default="")),
                ("house", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="flocks", to="core.house")),
                ("season", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="flocks", to="core.season")),
            ],
        ),
    ]
