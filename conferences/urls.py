from django.urls import path

from . import views


app_name = "conferences"

urlpatterns = [
    path(
        "conferences/<slug:event_slug>/programme/",
        views.public_programme,
        name="public_programme",
    ),
    path("staff/conferences/", views.conference_list, name="conference_list"),
    path(
        "staff/conferences/forms/<int:form_id>/",
        views.conference_detail,
        name="conference_detail",
    ),
    path(
        "staff/conferences/forms/<int:form_id>/registrations/<int:submission_id>/<str:decision>/",
        views.registration_decision,
        name="registration_decision",
    ),
    path(
        "staff/conferences/forms/<int:form_id>/sessions/<int:session_id>/register/",
        views.session_register,
        name="session_register",
    ),
    path(
        "staff/conferences/forms/<int:form_id>/sessions/<int:session_id>/register/export/",
        views.session_register_csv,
        name="session_register_csv",
    ),
    path(
        "staff/conferences/forms/<int:form_id>/qr/",
        views.registration_qr,
        name="registration_qr",
    ),
]
