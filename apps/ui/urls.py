from __future__ import annotations

from django.contrib.auth import views as auth_views
from django.urls import path

from .forms import BootstrapAuthenticationForm
from . import views

app_name = "ui"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("series/new/", views.create_series, name="create_series"),

    path("mortality/<int:pk>/edit/", views.mortality_edit, name="mortality_edit"),
    path("mortality/<int:pk>/delete/", views.mortality_delete, name="mortality_delete"),

    path("history/", views.history, name="history"),

    # Sales UI
    path("sales/", views.sales_list, name="sales_list"),
    path("sales/new/", views.sale_create, name="sale_create"),
    path("sales/<int:pk>/edit/", views.sale_edit, name="sale_edit"),
    path("sales/<int:pk>/delete/", views.sale_delete, name="sale_delete"),

    
    # Sales quick (design clasic) + export + plăți
    path("sales/quick/", views.sales_quick, name="sales_quick"),
    path("sales/export.csv", views.sales_export_csv, name="sales_export_csv"),
    path("payments/<int:pk>/paid/", views.payment_mark_paid, name="payment_mark_paid"),

# Users provisioning (ADMIN only)
    path("users/", views.users_list, name="users_list"),
    path("users/new/", views.user_create, name="user_create"),

    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="ui/login.html",
            authentication_form=BootstrapAuthenticationForm,
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
