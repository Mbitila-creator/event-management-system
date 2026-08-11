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
        "staff/special-events/participants/cards.zip",
        views.special_event_participant_cards_zip,
        name="special_event_participant_cards_zip",
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
    path(
        "special-events/participants/<uuid:token>/card.png",
        views.special_event_participant_card_download,
        name="special_event_participant_card_download",
    ),
    path(
        "special-events/participants/<uuid:token>/qr-download.png",
        views.special_event_participant_qr_download,
        name="special_event_participant_qr_download",
    ),
    path(
        "special-events/participants/<uuid:token>/text.png",
        views.special_event_participant_text_download,
        name="special_event_participant_text_download",
    ),
]
