from __future__ import annotations

from django.urls import path
from django.contrib.auth import views as auth_views

from .forms import BootstrapAuthenticationForm
from . import views

app_name = "ui"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("series/new/", views.create_series, name="create_series"),

    # Utilizatori (doar ADMIN)
    path("users/", views.users_list, name="users_list"),
    path("users/new/", views.user_create, name="user_create"),

    # Accesări (LOGIN/LOGOUT)
    path("access/", views.access_history, name="access_history"),

    path("mortality/<int:pk>/edit/", views.mortality_edit, name="mortality_edit"),
    path("mortality/<int:pk>/delete/", views.mortality_delete, name="mortality_delete"),

    path("history/", views.history, name="history"),

    # Vânzări
    path("sales/<int:pk>/delete/", views.sale_delete, name="sale_delete"),
    path("sales/export.csv", views.sales_export_csv, name="sales_export_csv"),
    path("sales/export.xlsx", views.sales_export_xlsx, name="sales_export_xlsx"),
    path("payments/ledger/", views.payment_ledger, name="payment_ledger"),
    path("payments/<int:pk>/edit/", views.payment_edit, name="payment_edit"),
    path("payments/<int:pk>/delete/", views.payment_delete, name="payment_delete"),
    path("payments/<int:pk>/paid/", views.payment_mark_paid, name="payment_mark_paid"),

    path("login/", auth_views.LoginView.as_view(
        template_name="ui/login.html",
        authentication_form=BootstrapAuthenticationForm,
    ), name="login"),
    # Logout: redirect imediat către login (și merge atât cu GET, cât și cu POST)
    path("logout/", auth_views.LogoutView.as_view(next_page="/login/"), name="logout"),
]
