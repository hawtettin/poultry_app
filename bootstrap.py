# bootstrap.py
# Genereaza un MVP Django + DRF + Postgres (Docker) pentru ferma avicola.
# Rulare: python bootstrap.py

from __future__ import annotations
from pathlib import Path

BASE = Path(__file__).resolve().parent
FILES: dict[str, str] = {}

def add(path: str, content: str) -> None:
    FILES[path] = content.replace("\r\n", "\n")

# -------------------------
# Root files
# -------------------------
add("requirements.txt", """\
Django==5.1.4
djangorestframework==3.15.2
psycopg2-binary==2.9.9
dj-database-url==2.3.0
python-dotenv==1.0.1
""")

add(".env.example", """\
DJANGO_SECRET_KEY=dev-secret-change-me
DJANGO_DEBUG=1
DATABASE_URL=postgres://poultry:poultry@localhost:5432/poultry
""")

add("docker-compose.yml", """\
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: poultry
      POSTGRES_USER: poultry
      POSTGRES_PASSWORD: poultry
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
""")

add("manage.py", """\
#!/usr/bin/env python
import os
import sys

def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)

if __name__ == "__main__":
    main()
""")

# -------------------------
# Django config
# -------------------------
add("config/__init__.py", "")

add("config/settings.py", """\
from __future__ import annotations

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env", override=False)
load_dotenv(BASE_DIR / ".env.example", override=False)

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-secret")
DEBUG = os.getenv("DJANGO_DEBUG", "0") in ("1", "true", "True", "yes", "YES")

ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "rest_framework",

    "apps.accounts",
    "apps.core",
    "apps.health",
    "apps.finance",
    "apps.reports",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=os.getenv("DATABASE_URL", "sqlite:///db.sqlite3"),
        conn_max_age=600,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ro-ro"
TIME_ZONE = "Europe/Bucharest"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}
""")

add("config/urls.py", """\
from __future__ import annotations

from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.core.api import HouseViewSet, SeasonViewSet, FlockViewSet
from apps.health.api import MortalityViewSet, TreatmentViewSet, WithdrawalAlertsView
from apps.finance.api import PartnerViewSet, CategoryViewSet, DocumentViewSet, PaymentViewSet
from apps.reports.api import SeasonReportView

router = DefaultRouter()
router.register(r"houses", HouseViewSet, basename="house")
router.register(r"seasons", SeasonViewSet, basename="season")
router.register(r"flocks", FlockViewSet, basename="flock")

router.register(r"mortalities", MortalityViewSet, basename="mortality")
router.register(r"treatments", TreatmentViewSet, basename="treatment")

router.register(r"partners", PartnerViewSet, basename="partner")
router.register(r"categories", CategoryViewSet, basename="category")
router.register(r"documents", DocumentViewSet, basename="document")
router.register(r"payments", PaymentViewSet, basename="payment")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    path("api/alerts/withdrawal/", WithdrawalAlertsView.as_view(), name="withdrawal-alerts"),
    path("api/reports/season/<int:season_id>/", SeasonReportView.as_view(), name="season-report"),
    path("api/auth/", include("rest_framework.urls")),
]
""")

add("config/wsgi.py", """\
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_wsgi_application()
""")

# -------------------------
# Apps package
# -------------------------
add("apps/__init__.py", "")

# -------------------------
# Accounts (roles/groups + permissions)
# -------------------------
add("apps/accounts/__init__.py", "")

add("apps/accounts/apps.py", """\
from django.apps import AppConfig

class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
""")

add("apps/accounts/permissions.py", """\
from __future__ import annotations
from rest_framework.permissions import BasePermission

def in_group(user, name: str) -> bool:
    return user.is_authenticated and user.groups.filter(name=name).exists()

class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and (u.is_superuser or in_group(u, "ADMIN"))

class IsManagerOrAdmin(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and (u.is_superuser or in_group(u, "ADMIN") or in_group(u, "MANAGER"))

class IsEmployeeOrAbove(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and (
            u.is_superuser or in_group(u, "ADMIN") or in_group(u, "MANAGER") or in_group(u, "EMPLOYEE")
        )
""")

add("apps/accounts/management/__init__.py", "")
add("apps/accounts/management/commands/__init__.py", "")

add("apps/accounts/management/commands/init_roles.py", """\
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group

ROLE_NAMES = ["ADMIN", "MANAGER", "EMPLOYEE"]

class Command(BaseCommand):
    help = "Creeaza grupurile de roluri: ADMIN, MANAGER, EMPLOYEE"

    def handle(self, *args, **options):
        for name in ROLE_NAMES:
            Group.objects.get_or_create(name=name)
        self.stdout.write(self.style.SUCCESS("OK: Grupurile au fost create/exista deja."))
""")

# -------------------------
# Core (houses/seasons/flocks)
# -------------------------
add("apps/core/__init__.py", "")
add("apps/core/apps.py", """\
from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
""")

add("apps/core/migrations/__init__.py", "")

add("apps/core/models.py", """\
from __future__ import annotations
from django.db import models

class House(models.Model):
    name = models.CharField(max_length=120, unique=True)
    code = models.CharField(max_length=50, blank=True, default="")

    def __str__(self) -> str:
        return self.name

class Season(models.Model):
    name = models.CharField(max_length=120, unique=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name

class Flock(models.Model):
    season = models.ForeignKey(Season, on_delete=models.PROTECT, related_name="flocks")
    house = models.ForeignKey(House, on_delete=models.PROTECT, related_name="flocks")
    start_date = models.DateField()
    initial_count = models.PositiveIntegerField()
    breed = models.CharField(max_length=120, blank=True, default="")
    supplier = models.CharField(max_length=120, blank=True, default="")
    notes = models.TextField(blank=True, default="")

    def __str__(self) -> str:
        return f"{self.season.name} / {self.house.name} ({self.start_date})"
""")

add("apps/core/admin.py", """\
from django.contrib import admin
from .models import House, Season, Flock

@admin.register(House)
class HouseAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "code")
    search_fields = ("name", "code")

@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "start_date", "end_date", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)

@admin.register(Flock)
class FlockAdmin(admin.ModelAdmin):
    list_display = ("id", "season", "house", "start_date", "initial_count", "breed", "supplier")
    list_filter = ("season", "house")
""")

add("apps/core/api.py", """\
from __future__ import annotations
from rest_framework import serializers, viewsets

from apps.accounts.permissions import IsEmployeeOrAbove, IsManagerOrAdmin
from .models import House, Season, Flock

class HouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = House
        fields = ["id", "name", "code"]

class SeasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Season
        fields = ["id", "name", "start_date", "end_date", "is_active"]

class FlockSerializer(serializers.ModelSerializer):
    class Meta:
        model = Flock
        fields = ["id", "season", "house", "start_date", "initial_count", "breed", "supplier", "notes"]

class HouseViewSet(viewsets.ModelViewSet):
    queryset = House.objects.all().order_by("name")
    serializer_class = HouseSerializer
    permission_classes = [IsManagerOrAdmin]

class SeasonViewSet(viewsets.ModelViewSet):
    queryset = Season.objects.all().order_by("-start_date")
    serializer_class = SeasonSerializer
    permission_classes = [IsManagerOrAdmin]

class FlockViewSet(viewsets.ModelViewSet):
    queryset = Flock.objects.select_related("season", "house").all().order_by("-start_date")
    serializer_class = FlockSerializer
    permission_classes = [IsEmployeeOrAbove]
""")

# -------------------------
# Health (mortalities + treatments + withdrawal alerts)
# -------------------------
add("apps/health/__init__.py", "")
add("apps/health/apps.py", """\
from django.apps import AppConfig

class HealthConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.health"
""")

add("apps/health/migrations/__init__.py", "")

add("apps/health/models.py", """\
from __future__ import annotations
from datetime import timedelta
from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import Flock

class MortalityEvent(models.Model):
    flock = models.ForeignKey(Flock, on_delete=models.CASCADE, related_name="mortality_events")
    date = models.DateField(default=timezone.localdate)
    count = models.PositiveIntegerField()
    reason = models.CharField(max_length=120, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

class Treatment(models.Model):
    METHOD_CHOICES = [
        ("water", "Apa"),
        ("feed", "Furaj"),
        ("injection", "Injectie"),
        ("other", "Altul"),
    ]

    flock = models.ForeignKey(Flock, on_delete=models.CASCADE, related_name="treatments")
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(default=timezone.localdate)
    product_name = models.CharField(max_length=150)
    active_substance = models.CharField(max_length=150, blank=True, default="")
    dose = models.CharField(max_length=120, blank=True, default="")
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default="water")
    withdrawal_days = models.PositiveIntegerField(default=0)
    withdrawal_end_date = models.DateField(null=True, blank=True)

    vet_name = models.CharField(max_length=120, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date", "-id"]

    def save(self, *args, **kwargs):
        self.withdrawal_end_date = self.end_date + timedelta(days=int(self.withdrawal_days or 0))
        super().save(*args, **kwargs)
""")

add("apps/health/admin.py", """\
from django.contrib import admin
from .models import MortalityEvent, Treatment

@admin.register(MortalityEvent)
class MortalityAdmin(admin.ModelAdmin):
    list_display = ("id", "flock", "date", "count", "reason", "created_by")
    list_filter = ("date", "flock")

@admin.register(Treatment)
class TreatmentAdmin(admin.ModelAdmin):
    list_display = ("id", "flock", "product_name", "start_date", "end_date", "withdrawal_days", "withdrawal_end_date", "method")
    list_filter = ("method", "start_date", "flock")
""")

add("apps/health/api.py", """\
from __future__ import annotations
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.accounts.permissions import IsEmployeeOrAbove
from .models import MortalityEvent, Treatment

class MortalitySerializer(serializers.ModelSerializer):
    class Meta:
        model = MortalityEvent
        fields = ["id", "flock", "date", "count", "reason", "notes", "created_by", "created_at"]
        read_only_fields = ["created_by", "created_at"]

class TreatmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Treatment
        fields = [
            "id", "flock",
            "start_date", "end_date",
            "product_name", "active_substance",
            "dose", "method",
            "withdrawal_days", "withdrawal_end_date",
            "vet_name", "notes",
            "created_by", "created_at",
        ]
        read_only_fields = ["withdrawal_end_date", "created_by", "created_at"]

class MortalityViewSet(viewsets.ModelViewSet):
    queryset = MortalityEvent.objects.select_related("flock").all()
    serializer_class = MortalitySerializer
    permission_classes = [IsEmployeeOrAbove]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

class TreatmentViewSet(viewsets.ModelViewSet):
    queryset = Treatment.objects.select_related("flock").all()
    serializer_class = TreatmentSerializer
    permission_classes = [IsEmployeeOrAbove]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

class WithdrawalAlertsView(APIView):
    permission_classes = [IsEmployeeOrAbove]

    def get(self, request):
        today = timezone.localdate()
        qs = Treatment.objects.filter(withdrawal_end_date__gte=today).order_by("withdrawal_end_date")
        return Response({
            "today": str(today),
            "active_withdrawals": TreatmentSerializer(qs, many=True).data
        })
""")

# -------------------------
# Finance (partners, categories, documents, payments)
# -------------------------
add("apps/finance/__init__.py", "")
add("apps/finance/apps.py", """\
from django.apps import AppConfig

class FinanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.finance"
""")

add("apps/finance/migrations/__init__.py", "")

add("apps/finance/models.py", """\
from __future__ import annotations
from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import Season, Flock

class Partner(models.Model):
    PARTNER_TYPES = [
        ("supplier", "Furnizor"),
        ("client", "Client"),
        ("other", "Altul"),
    ]
    name = models.CharField(max_length=200, unique=True)
    partner_type = models.CharField(max_length=20, choices=PARTNER_TYPES, default="other")
    tax_id = models.CharField(max_length=50, blank=True, default="")
    phone = models.CharField(max_length=50, blank=True, default="")
    email = models.CharField(max_length=120, blank=True, default="")
    notes = models.TextField(blank=True, default="")

    def __str__(self) -> str:
        return self.name

class Category(models.Model):
    KIND = [("expense", "Cheltuiala"), ("income", "Venit")]
    name = models.CharField(max_length=120, unique=True)
    kind = models.CharField(max_length=10, choices=KIND, default="expense")

    def __str__(self) -> str:
        return f"{self.name} ({self.kind})"

class Document(models.Model):
    DOC_TYPES = [("expense", "Cheltuiala"), ("sale", "Vanzare")]
    STATUS = [("draft", "Draft"), ("approved", "Aprobat"), ("locked", "Blocat")]

    doc_type = models.CharField(max_length=10, choices=DOC_TYPES)
    status = models.CharField(max_length=10, choices=STATUS, default="draft")

    season = models.ForeignKey(Season, on_delete=models.PROTECT, related_name="documents")
    flock = models.ForeignKey(Flock, null=True, blank=True, on_delete=models.PROTECT, related_name="documents")
    partner = models.ForeignKey(Partner, null=True, blank=True, on_delete=models.PROTECT, related_name="documents")

    doc_no = models.CharField(max_length=80, blank=True, default="")
    date = models.DateField(default=timezone.localdate)
    currency = models.CharField(max_length=10, default="RON")

    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    vat = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    notes = models.TextField(blank=True, default="")

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_documents")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def recalc_totals(self):
        subtotal = sum((ln.line_total for ln in self.lines.all()), Decimal("0.00"))
        self.subtotal = subtotal
        self.total = (self.subtotal + self.vat).quantize(Decimal("0.01"))

class DocumentLine(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="lines")
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.PROTECT)
    description = models.CharField(max_length=250, blank=True, default="")
    qty = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("1.000"))
    unit = models.CharField(max_length=20, blank=True, default="")
    unit_price = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("0.0000"))
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    def save(self, *args, **kwargs):
        self.line_total = (self.qty * self.unit_price).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)
        self.document.recalc_totals()
        self.document.save(update_fields=["subtotal", "total"])

class Payment(models.Model):
    METHODS = [("cash", "Cash"), ("bank", "Banca"), ("card", "Card"), ("other", "Altul")]
    STATUS = [("due", "Scadent"), ("paid", "Platit")]

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="payments")
    due_date = models.DateField()
    paid_date = models.DateField(null=True, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    method = models.CharField(max_length=10, choices=METHODS, default="bank")
    status = models.CharField(max_length=10, choices=STATUS, default="due")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["status", "due_date", "-id"]
""")

add("apps/finance/admin.py", """\
from django.contrib import admin
from .models import Partner, Category, Document, DocumentLine, Payment

@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "partner_type", "tax_id")
    list_filter = ("partner_type",)
    search_fields = ("name", "tax_id")

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "kind")
    list_filter = ("kind",)

class DocumentLineInline(admin.TabularInline):
    model = DocumentLine
    extra = 1

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "doc_type", "status", "doc_no", "date", "season", "flock", "partner", "total", "currency")
    list_filter = ("doc_type", "status", "season")
    inlines = [DocumentLineInline]

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "status", "due_date", "paid_date", "amount", "method")
    list_filter = ("status", "method")
""")

add("apps/finance/api.py", """\
from __future__ import annotations
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsEmployeeOrAbove, IsManagerOrAdmin
from .models import Partner, Category, Document, DocumentLine, Payment

class PartnerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Partner
        fields = ["id", "name", "partner_type", "tax_id", "phone", "email", "notes"]

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "kind"]

class DocumentLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentLine
        fields = ["id", "category", "description", "qty", "unit", "unit_price", "line_total"]
        read_only_fields = ["line_total"]

class DocumentSerializer(serializers.ModelSerializer):
    lines = DocumentLineSerializer(many=True, required=False)

    class Meta:
        model = Document
        fields = [
            "id", "doc_type", "status",
            "season", "flock", "partner",
            "doc_no", "date", "currency",
            "subtotal", "vat", "total",
            "notes",
            "created_by", "created_at",
            "lines",
        ]
        read_only_fields = ["subtotal", "total", "created_by", "created_at"]

    def create(self, validated_data):
        lines_data = validated_data.pop("lines", [])
        doc = Document.objects.create(**validated_data)
        for ln in lines_data:
            DocumentLine.objects.create(document=doc, **ln)
        doc.recalc_totals()
        doc.save(update_fields=["subtotal", "total"])
        return doc

    def update(self, instance, validated_data):
        lines_data = validated_data.pop("lines", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        if lines_data is not None:
            instance.lines.all().delete()
            for ln in lines_data:
                DocumentLine.objects.create(document=instance, **ln)
            instance.recalc_totals()
            instance.save(update_fields=["subtotal", "total"])
        return instance

class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["id", "document", "due_date", "paid_date", "amount", "method", "status", "created_by"]
        read_only_fields = ["created_by"]

class PartnerViewSet(viewsets.ModelViewSet):
    queryset = Partner.objects.all().order_by("name")
    serializer_class = PartnerSerializer
    permission_classes = [IsManagerOrAdmin]

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all().order_by("name")
    serializer_class = CategorySerializer
    permission_classes = [IsManagerOrAdmin]

class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.select_related("season", "flock", "partner").prefetch_related("lines").all()
    serializer_class = DocumentSerializer
    permission_classes = [IsEmployeeOrAbove]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"], permission_classes=[IsManagerOrAdmin])
    def approve(self, request, pk=None):
        doc = self.get_object()
        if doc.status == "locked":
            return Response({"detail": "Document locked."}, status=400)
        doc.status = "approved"
        doc.save(update_fields=["status"])
        return Response({"detail": "Approved", "id": doc.id, "status": doc.status})

class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.select_related("document").all()
    serializer_class = PaymentSerializer
    permission_classes = [IsEmployeeOrAbove]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
""")

# -------------------------
# Reports
# -------------------------
add("apps/reports/__init__.py", "")
add("apps/reports/apps.py", """\
from django.apps import AppConfig

class ReportsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reports"
""")

add("apps/reports/migrations/__init__.py", "")

add("apps/reports/api.py", """\
from __future__ import annotations
from decimal import Decimal
from django.db.models import Sum
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.accounts.permissions import IsManagerOrAdmin
from apps.finance.models import Document, DocumentLine

class SeasonReportView(APIView):
    permission_classes = [IsManagerOrAdmin]

    def get(self, request, season_id: int):
        sales = Document.objects.filter(season_id=season_id, doc_type="sale").aggregate(total=Sum("total"))["total"] or Decimal("0.00")
        expenses = Document.objects.filter(season_id=season_id, doc_type="expense").aggregate(total=Sum("total"))["total"] or Decimal("0.00")
        profit = (sales - expenses).quantize(Decimal("0.01"))

        top_exp = (
            DocumentLine.objects
            .filter(document__season_id=season_id, document__doc_type="expense")
            .values("category__name")
            .annotate(total=Sum("line_total"))
            .order_by("-total")[:10]
        )

        return Response({
            "season_id": season_id,
            "sales_total": str(sales),
            "expenses_total": str(expenses),
            "profit": str(profit),
            "top_expenses_by_category": list(top_exp),
        })
""")

def write_files() -> None:
    for rel, content in FILES.items():
        p = BASE / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    print("✅ OK: Proiect generat.")
    print("➡️ Urmatorii pasi (CMD):")
    print("   copy .env.example .env")
    print("   python -m venv .venv")
    print("   .venv\\Scripts\\activate.bat")
    print("   pip install -r requirements.txt")
    print("   docker compose up -d")
    print("   python manage.py makemigrations")
    print("   python manage.py migrate")
    print("   python manage.py init_roles")
    print("   python manage.py createsuperuser")
    print("   python manage.py runserver")

if __name__ == "__main__":
    write_files()
