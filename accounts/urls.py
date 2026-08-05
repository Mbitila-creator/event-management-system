from django.contrib.auth.views import LoginView
from django.urls import path, reverse_lazy

from . import views


app_name = "accounts"

urlpatterns = [
    path(
        "staff/login/",
        LoginView.as_view(
            template_name="accounts/staff_login.html",
            redirect_authenticated_user=True,
            next_page=reverse_lazy("accounts:role_home"),
        ),
        name="staff_login",
    ),
    path("staff/", views.role_home, name="role_home"),
    path("staff/logout/", views.staff_logout, name="staff_logout"),
]
