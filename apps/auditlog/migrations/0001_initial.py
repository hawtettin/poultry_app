# Generated manually for this project (compatible with Django 5.1.x)
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("action", models.CharField(choices=[("CREATE","CREATE"),("UPDATE","UPDATE"),("DELETE","DELETE")], max_length=10)),
                ("model", models.CharField(max_length=120)),
                ("object_id", models.CharField(max_length=64)),
                ("message", models.CharField(blank=True, default="", max_length=300)),
                ("before", models.JSONField(blank=True, null=True)),
                ("after", models.JSONField(blank=True, null=True)),
                ("path", models.CharField(blank=True, default="", max_length=300)),
                ("method", models.CharField(blank=True, default="", max_length=10)),
                ("ip_address", models.CharField(blank=True, default="", max_length=45)),
                ("user_agent", models.CharField(blank=True, default="", max_length=500)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="audit_events", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=["created_at"], name="auditlog_a_created_9c9b6f_idx"),
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=["actor", "created_at"], name="auditlog_a_actor_c_f51b7f_idx"),
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=["model", "created_at"], name="auditlog_a_model_c_8b5c52_idx"),
        ),
    ]
