from django.urls import path

from . import views


app_name = "conferences"

urlpatterns = [
    path("staff/conferences/", views.conference_list, name="conference_list"),
    path(
        "staff/conferences/forms/<int:form_id>/qr/",
        views.registration_qr,
        name="registration_qr",
    ),
]
