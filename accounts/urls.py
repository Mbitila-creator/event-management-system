from django.contrib.auth.views import (
    LoginView,
    PasswordChangeDoneView,
    PasswordChangeView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
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
    path(
        "staff/password/change/",
        PasswordChangeView.as_view(
            template_name="accounts/password_change_form.html",
            success_url=reverse_lazy("accounts:password_change_done"),
        ),
        name="password_change",
    ),
    path(
        "staff/password/change/done/",
        PasswordChangeDoneView.as_view(
            template_name="accounts/password_change_done.html",
        ),
        name="password_change_done",
    ),
    path(
        "staff/password/reset/",
        PasswordResetView.as_view(
            template_name="accounts/password_reset_form.html",
            email_template_name="accounts/password_reset_email.txt",
            subject_template_name="accounts/password_reset_subject.txt",
            success_url=reverse_lazy("accounts:password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "staff/password/reset/done/",
        PasswordResetDoneView.as_view(
            template_name="accounts/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "staff/password/reset/<uidb64>/<token>/",
        PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url=reverse_lazy("accounts:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "staff/password/reset/complete/",
        PasswordResetCompleteView.as_view(
            template_name="accounts/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),
    path("staff/", views.role_home, name="role_home"),
    path(
        "staff/participants/<int:submission_id>/review/",
        views.participant_review_details,
        name="participant_review_details",
    ),
    path("staff/booths/", views.booth_assignments, name="booth_assignments"),
    path(
        "staff/booths/<int:booth_id>/update/",
        views.update_booth_assignment,
        name="update_booth_assignment",
    ),
    path(
        "staff/registrations/<int:submission_id>/<str:decision>/",
        views.review_registration,
        name="review_registration",
    ),
    path(
        "staff/payments/<int:payment_id>/<str:decision>/",
        views.review_payment,
        name="review_payment",
    ),
    path(
        "staff/certificates/<int:submission_id>/<str:decision>/",
        views.update_certificate_authorization,
        name="update_certificate_authorization",
    ),
    path("staff/logout/", views.staff_logout, name="staff_logout"),
]
