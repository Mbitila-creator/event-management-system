from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from accounts.models import User
from forms_builder.models import EventForm
from forms_builder.services import generate_qr_png, public_form_path, public_form_url


CONFERENCE_VIEW_ROLES = {
    User.Role.SYSTEM_ADMIN,
    User.Role.EVENT_ADMIN,
    User.Role.ATTENDANCE_OFFICER,
    User.Role.REPORT_OFFICER,
    User.Role.DIRECTOR,
    User.Role.ASSISTANT_DIRECTOR,
}


def _require_access(user):
    if not (
        user.is_authenticated
        and user.is_active
        and (user.is_superuser or user.role in CONFERENCE_VIEW_ROLES)
    ):
        raise PermissionDenied


def _conference_registration_forms():
    return (
        EventForm.objects.filter(
            Q(event__category__code__iexact="CONFERENCE")
            | Q(event__category__name_en__iexact="Conference")
            | Q(event__category__slug__in=("conference", "kongamano")),
            form_type=EventForm.FormType.REGISTRATION,
            is_active=True,
        )
        .select_related("event", "event__venue")
        .order_by("-event__starts_at", "event__code")
    )


@login_required
def conference_list(request):
    _require_access(request.user)
    registrations = []
    for event_form in _conference_registration_forms():
        registrations.append({
            "form": event_form,
            "public_path": public_form_path(event_form, language="en"),
            "submission_count": event_form.submissions.filter(
                is_complete=True,
            ).count(),
        })
    return render(
        request,
        "conferences/conference_list.html",
        {"registrations": registrations},
    )


@login_required
def registration_qr(request, form_id):
    _require_access(request.user)
    event_form = get_object_or_404(
        _conference_registration_forms(),
        pk=form_id,
        is_published=True,
    )
    registration_url = public_form_url(
        event_form,
        request=request,
        language="en",
    )
    response = HttpResponse(
        generate_qr_png(registration_url),
        content_type="image/png",
    )
    if request.GET.get("download") == "1":
        response["Content-Disposition"] = (
            f'attachment; filename="{event_form.event.code}-registration-QR.png"'
        )
    response["X-Content-Type-Options"] = "nosniff"
    return response
