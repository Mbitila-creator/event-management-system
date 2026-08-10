from django.urls import path

from . import views


app_name = "events"

urlpatterns = [
    path(
        "",
        views.home,
        name="home",
    ),
    path(
        "events/<slug:event_slug>/",
        views.event_detail,
        name="event_detail",
    ),
    path(
        "staff/special-events/participants/",
        views.special_event_participant_list,
        name="special_event_participant_list",
    ),
    path(
        "staff/special-events/participants/import/",
        views.special_event_participant_import,
        name="special_event_participant_import",
    ),
    path(
        "staff/special-events/participants/print/",
        views.special_event_participant_print,
        name="special_event_participant_print",
    ),
    path(
        "special-events/participants/<uuid:token>/",
        views.special_event_participant_verify,
        name="special_event_participant_verify",
    ),
    path(
        "special-events/participants/<uuid:token>/qr.png",
        views.special_event_participant_qr,
        name="special_event_participant_qr",
    ),
]
