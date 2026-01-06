from __future__ import annotations

from django.contrib import admin
from django.urls import include, path

from django.conf import settings
from django.conf.urls.static import static
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
    path("", include("apps.ui.urls")),
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    path("api/alerts/withdrawal/", WithdrawalAlertsView.as_view(), name="withdrawal-alerts"),
    path("api/reports/season/<int:season_id>/", SeasonReportView.as_view(), name="season-report"),
    path("api/auth/", include("rest_framework.urls")),
]


# Servește fișierele media (atașamente) în mod DEV.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
