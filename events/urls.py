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
]