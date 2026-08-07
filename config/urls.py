from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from forms_builder.views import run_due_reminders


urlpatterns = [
    path("i18n/", include("django.conf.urls.i18n")),
    path(
        "automation/reminders/run/",
        run_due_reminders,
        name="run_due_reminders",
    ),
]


urlpatterns += i18n_patterns(
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("", include("events.urls")),
    path("", include("forms_builder.urls")),
    path("", include("checkin.urls")),
    path("", include("meetings.urls")),
)


if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )
