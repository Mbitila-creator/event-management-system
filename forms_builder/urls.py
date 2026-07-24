from django.urls import path

from . import views


app_name = "forms_builder"

urlpatterns = [
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