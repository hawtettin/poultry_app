from __future__ import annotations

from django.urls import path
from django.contrib.auth import views as auth_views

from .forms import BootstrapAuthenticationForm
from . import views

app_name = "ui"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("series/new/", views.create_series, name="create_series"),

    path("mortality/<int:pk>/edit/", views.mortality_edit, name="mortality_edit"),
    path("mortality/<int:pk>/delete/", views.mortality_delete, name="mortality_delete"),

    path("history/", views.history, name="history"),

    # Vânzări
    path("sales/export.csv", views.sales_export_csv, name="sales_export_csv"),
    path("payments/<int:pk>/paid/", views.payment_mark_paid, name="payment_mark_paid"),

    path("login/", auth_views.LoginView.as_view(
        template_name="ui/login.html",
        authentication_form=BootstrapAuthenticationForm,
    ), name="login"),
    path("logout/", views.logout_redirect, name="logout"),
]
