from django.urls import path

from . import views


app_name = "meetings"

urlpatterns = [
    path("staff/meetings/", views.meeting_list, name="meeting_list"),
    path("staff/meetings/new/", views.meeting_create, name="meeting_create"),
    path(
        "staff/meetings/<int:meeting_id>/",
        views.meeting_detail,
        name="meeting_detail",
    ),
    path(
        "staff/meetings/<int:meeting_id>/edit/",
        views.meeting_edit,
        name="meeting_edit",
    ),
    path(
        "staff/meetings/<int:meeting_id>/agenda/add/",
        views.agenda_add,
        name="agenda_add",
    ),
    path(
        "staff/meetings/<int:meeting_id>/participants/add/",
        views.attendee_add,
        name="attendee_add",
    ),
    path(
        "staff/meetings/<int:meeting_id>/participants/<int:attendee_id>/update/",
        views.attendee_update,
        name="attendee_update",
    ),
    path(
        "staff/meetings/<int:meeting_id>/participants/<int:attendee_id>/invite/",
        views.invitation_send,
        name="invitation_send",
    ),
    path(
        "staff/meetings/<int:meeting_id>/minutes/update/",
        views.minutes_update,
        name="minutes_update",
    ),
    path(
        "staff/meetings/<int:meeting_id>/decisions/add/",
        views.decision_add,
        name="decision_add",
    ),
    path(
        "staff/meetings/<int:meeting_id>/actions/add/",
        views.action_add,
        name="action_add",
    ),
    path(
        "staff/meetings/<int:meeting_id>/actions/<int:action_id>/update/",
        views.action_update,
        name="action_update",
    ),
    path(
        "meetings/invitations/<uuid:response_token>/",
        views.invitation_response,
        name="invitation_response",
    ),
]
