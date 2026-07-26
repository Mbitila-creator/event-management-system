from django.urls import path

from . import views


app_name = "forms_builder"

urlpatterns = [
    path(
        "participants/<uuid:participant_token>/certificate/",
        views.participant_certificate,
        name="participant_certificate",
    ),
    path(
        "participants/<uuid:participant_token>/badge/",
        views.participant_badge,
        name="participant_badge",
    ),
    path(
        "participants/<uuid:participant_token>/badge/qr/",
        views.participant_badge_qr,
        name="participant_badge_qr",
    ),
    path(
        "registration-status/",
        views.registration_status,
        name="registration_status",
    ),
    path(
        "events/<slug:event_slug>/forms/<slug:form_slug>/",
        views.public_event_form,
        name="public_event_form",
    ),
    path(
        "submissions/<str:reference_number>/success/",
        views.submission_success,
        name="submission_success",
    ),
]
