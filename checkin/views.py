from django.contrib.auth.decorators import user_passes_test
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts.models import User
from forms_builder.models import FormSubmission
from forms_builder.services import participant_certificate_path

from .models import ParticipantCheckIn


CHECK_IN_ROLES = {
    User.Role.SYSTEM_ADMIN,
    User.Role.EVENT_ADMIN,
    User.Role.REGISTRATION_OFFICER,
    User.Role.ATTENDANCE_OFFICER,
}


def can_check_in(user):
    return bool(
        user.is_authenticated
        and (
            user.is_superuser
            or user.is_staff
            or user.role in CHECK_IN_ROLES
        )
    )


check_in_required = user_passes_test(
    can_check_in,
    login_url="admin:login",
)


def approved_submission_queryset():
    return FormSubmission.objects.select_related(
        "event_form",
        "event_form__event",
        "event_form__event__venue",
    ).filter(
        review_status=FormSubmission.ReviewStatus.APPROVED,
        is_complete=True,
        is_active=True,
        event_form__event__qr_checkin_enabled=True,
    )


@check_in_required
@require_http_methods(["GET", "POST"])
def check_in_lookup(request):
    lookup_error = ""

    if request.method == "POST":
        identifier = request.POST.get("identifier", "").strip()
        submission = approved_submission_queryset().filter(
            reference_number__iexact=identifier
        ).first()

        if submission is None:
            try:
                submission = approved_submission_queryset().filter(
                    participant_token=identifier
                ).first()
            except (TypeError, ValueError):
                submission = None

        if submission:
            return redirect(
                "checkin:participant",
                participant_token=submission.participant_token,
            )

        lookup_error = "Participant not found or not eligible for check-in."

    return render(
        request,
        "checkin/lookup.html",
        {"lookup_error": lookup_error},
    )


@check_in_required
@require_http_methods(["GET", "POST"])
def participant_check_in(request, participant_token):
    submission = get_object_or_404(
        FormSubmission.objects.select_related(
            "event_form",
            "event_form__event",
            "event_form__event__venue",
        ),
        participant_token=participant_token,
    )
    is_eligible = bool(
        submission.review_status
        == FormSubmission.ReviewStatus.APPROVED
        and submission.is_complete
        and submission.is_active
        and submission.event_form.event.qr_checkin_enabled
    )
    check_in = ParticipantCheckIn.objects.filter(
        submission=submission
    ).select_related("checked_in_by").first()
    just_checked_in = False
    automatic_check_in = (
        request.method == "GET" and request.GET.get("auto") == "1"
    )

    if (
        (request.method == "POST" or automatic_check_in)
        and check_in is None
        and is_eligible
    ):
        with transaction.atomic():
            locked_submission = (
                approved_submission_queryset()
                .select_for_update()
                .get(pk=submission.pk)
            )
            check_in, just_checked_in = (
                ParticipantCheckIn.objects.get_or_create(
                    submission=locked_submission,
                    defaults={
                        "checked_in_by": request.user,
                        "method": ParticipantCheckIn.Method.QR,
                        "created_by": request.user,
                        "updated_by": request.user,
                    },
                )
            )

    return render(
        request,
        "checkin/participant_check_in.html",
        {
            "submission": submission,
            "event": submission.event_form.event,
            "check_in": check_in,
            "just_checked_in": just_checked_in,
            "is_eligible": is_eligible,
            "certificate_path": (
                participant_certificate_path(
                    submission,
                    language=request.LANGUAGE_CODE,
                )
                if check_in and submission.event_form.event.certificate_enabled
                else ""
            ),
        },
    )
