from django.urls import path

from . import views


app_name = "forms_builder"

urlpatterns = [
    path(
        "events/<slug:event_slug>/forms/<slug:form_slug>/",
        views.public_event_form,
        name="public_event_form",
    ),
]