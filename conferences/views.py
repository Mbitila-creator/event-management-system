import csv
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from accounts.models import User
from events.models import Event
from forms_builder.models import EventForm, FormSubmission, NotificationLog
from forms_builder.notifications import send_submission_notification
from forms_builder.services import (
    generate_qr_png,
    public_form_path,
    public_form_url,
    safe_spreadsheet_value,
)

from .models import (
    ConferenceProgrammeContributor,
    ConferenceProgrammeItem,
    ConferenceSession,
    ConferenceSessionAttendance,
)


CONFERENCE_VIEW_ROLES = {
    User.Role.SYSTEM_ADMIN,
    User.Role.EVENT_ADMIN,
    User.Role.REGISTRATION_OFFICER,
    User.Role.ATTENDANCE_OFFICER,
    User.Role.REPORT_OFFICER,
    User.Role.DIRECTOR,
    User.Role.ASSISTANT_DIRECTOR,
}
CONFERENCE_MANAGER_ROLES = {
    User.Role.SYSTEM_ADMIN,
    User.Role.EVENT_ADMIN,
    User.Role.REGISTRATION_OFFICER,
}
CONFERENCE_CHECKIN_ROLES = CONFERENCE_MANAGER_ROLES | {
    User.Role.ATTENDANCE_OFFICER,
}
UUID_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}"
)


def _require_access(user):
    if not (
        user.is_authenticated
        and user.is_active
        and (user.is_superuser or user.role in CONFERENCE_VIEW_ROLES)
    ):
        raise PermissionDenied


def _require_manager(user):
    if not (
        user.is_authenticated
        and user.is_active
        and (user.is_superuser or user.role in CONFERENCE_MANAGER_ROLES)
    ):
        raise PermissionDenied


def _require_checkin(user):
    if not (
        user.is_authenticated
        and user.is_active
        and (user.is_superuser or user.role in CONFERENCE_CHECKIN_ROLES)
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


def _selected_submissions(event_form, session, approved_only=True):
    queryset = FormSubmission.objects.filter(
        event_form=event_form,
        is_active=True,
        is_complete=True,
        answers__question__section__event_form=event_form,
        answers__selected_options__value=session.registration_option_value,
        answers__selected_options__is_active=True,
    )
    if approved_only:
        queryset = queryset.filter(
            review_status=FormSubmission.ReviewStatus.APPROVED,
        )
    return queryset.distinct()


def _submission_session_values(submission):
    return set(
        submission.answers.filter(
            selected_options__isnull=False,
        ).values_list("selected_options__value", flat=True)
    )


@require_GET
def public_programme(request, event_slug):
    event = get_object_or_404(
        Event.objects.select_related("category", "venue"),
        slug=event_slug,
        is_active=True,
        is_public=True,
    )
    if not event.category.is_conference:
        raise PermissionDenied

    contributors = ConferenceProgrammeContributor.objects.filter(
        is_active=True,
        speaker__is_active=True,
    ).select_related("speaker")
    programme_items = ConferenceProgrammeItem.objects.filter(
        is_active=True,
        is_published=True,
    ).prefetch_related(
        Prefetch("contributors", queryset=contributors),
    )
    sessions = (
        ConferenceSession.objects.filter(event=event, is_active=True)
        .prefetch_related(
            Prefetch("programme_items", queryset=programme_items),
        )
        .order_by("starts_at", "display_order")
    )
    return render(
        request,
        "conferences/public_programme.html",
        {"event": event, "sessions": sessions},
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
def conference_detail(request, form_id):
    _require_access(request.user)
    event_form = get_object_or_404(_conference_registration_forms(), pk=form_id)
    submissions = list(
        event_form.submissions.filter(is_active=True, is_complete=True)
        .prefetch_related("answers__selected_options")
        .order_by("-created_at")
    )
    sessions = list(
        ConferenceSession.objects.filter(event=event_form.event, is_active=True)
        .prefetch_related("attendance_records")
        .order_by("starts_at", "display_order")
    )
    sessions_by_value = {
        session.registration_option_value: session for session in sessions
    }
    for submission in submissions:
        submission.selected_conference_sessions = [
            sessions_by_value[value]
            for value in _submission_session_values(submission)
            if value in sessions_by_value
        ]
    for session in sessions:
        session.registered_count = _selected_submissions(
            event_form,
            session,
        ).count()
        session.checked_in_count = session.attendance_records.filter(
            is_active=True,
        ).count()
    summary = {
        "total": len(submissions),
        "pending": sum(
            item.review_status == FormSubmission.ReviewStatus.PENDING
            for item in submissions
        ),
        "approved": sum(
            item.review_status == FormSubmission.ReviewStatus.APPROVED
            for item in submissions
        ),
        "rejected": sum(
            item.review_status == FormSubmission.ReviewStatus.REJECTED
            for item in submissions
        ),
    }
    return render(request, "conferences/conference_detail.html", {
        "event_form": event_form,
        "submissions": submissions,
        "sessions": sessions,
        "summary": summary,
        "can_manage": request.user.is_superuser
        or request.user.role in CONFERENCE_MANAGER_ROLES,
    })


@login_required
@require_POST
def registration_decision(request, form_id, submission_id, decision):
    _require_manager(request.user)
    event_form = get_object_or_404(_conference_registration_forms(), pk=form_id)
    submission = get_object_or_404(
        event_form.submissions,
        pk=submission_id,
        is_active=True,
        is_complete=True,
    )
    statuses = {
        "approve": FormSubmission.ReviewStatus.APPROVED,
        "reject": FormSubmission.ReviewStatus.REJECTED,
    }
    status = statuses.get(decision)
    if status is None:
        raise PermissionDenied
    reason = request.POST.get("reason", "").strip()
    if status == FormSubmission.ReviewStatus.REJECTED and not reason:
        messages.error(request, _("Enter a reason before rejecting the registration."))
        return redirect("conferences:conference_detail", form_id=event_form.pk)
    submission.review_status = status
    submission.reviewed_by = request.user
    submission.reviewed_at = timezone.now()
    submission.review_notes = reason if status == FormSubmission.ReviewStatus.REJECTED else ""
    submission.updated_by = request.user
    submission.save(update_fields=(
        "review_status",
        "reviewed_by",
        "reviewed_at",
        "review_notes",
        "updated_by",
        "updated_at",
    ))
    notification_type = (
        NotificationLog.NotificationType.REGISTRATION_APPROVED
        if status == FormSubmission.ReviewStatus.APPROVED
        else NotificationLog.NotificationType.REGISTRATION_REJECTED
    )
    send_submission_notification(submission, notification_type, request=request)
    messages.success(request, _("Registration status updated successfully."))
    return redirect("conferences:conference_detail", form_id=event_form.pk)


def _identifier_token(identifier):
    match = UUID_PATTERN.search(identifier)
    return match.group(0) if match else ""


@login_required
@require_http_methods(["GET", "POST"])
def session_register(request, form_id, session_id):
    _require_checkin(request.user)
    event_form = get_object_or_404(_conference_registration_forms(), pk=form_id)
    session = get_object_or_404(
        ConferenceSession,
        pk=session_id,
        event=event_form.event,
        is_active=True,
    )
    lookup_error = ""
    checked_submission = None
    if request.method == "POST":
        identifier = request.POST.get("identifier", "").strip()
        token = _identifier_token(identifier)
        candidates = FormSubmission.objects.filter(
            event_form=event_form,
            review_status=FormSubmission.ReviewStatus.APPROVED,
            is_active=True,
            is_complete=True,
        )
        checked_submission = candidates.filter(
            Q(reference_number__iexact=identifier)
            | Q(participant_token=token if token else None)
        ).first()
        if checked_submission is None:
            lookup_error = _("Participant not found or registration is not approved.")
        elif not _selected_submissions(
            event_form,
            session,
        ).filter(pk=checked_submission.pk).exists():
            lookup_error = _("This participant did not select this session.")
            checked_submission = None
        else:
            with transaction.atomic():
                attendance, created = ConferenceSessionAttendance.objects.get_or_create(
                    session=session,
                    submission=checked_submission,
                    defaults={
                        "checked_in_by": request.user,
                        "method": (
                            ConferenceSessionAttendance.Method.QR
                            if token
                            else ConferenceSessionAttendance.Method.MANUAL
                        ),
                        "created_by": request.user,
                        "updated_by": request.user,
                    },
                )
            if created:
                messages.success(
                    request,
                    _("%(name)s checked in successfully.")
                    % {"name": checked_submission.badge_display_name},
                )
            else:
                messages.info(
                    request,
                    _("This participant was already checked in to this session."),
                )
            return redirect(
                "conferences:session_register",
                form_id=event_form.pk,
                session_id=session.pk,
            )
    selected = list(
        _selected_submissions(event_form, session)
        .select_related("reviewed_by")
        .order_by("badge_name", "reference_number")
    )
    attendance_by_submission = {
        record.submission_id: record
        for record in session.attendance_records.filter(is_active=True)
        .select_related("checked_in_by")
    }
    for submission in selected:
        submission.session_attendance = attendance_by_submission.get(submission.pk)
    return render(request, "conferences/session_register.html", {
        "event_form": event_form,
        "session": session,
        "submissions": selected,
        "lookup_error": lookup_error,
        "checked_in_count": len(attendance_by_submission),
    })


@login_required
@require_GET
def session_register_csv(request, form_id, session_id):
    _require_access(request.user)
    event_form = get_object_or_404(_conference_registration_forms(), pk=form_id)
    session = get_object_or_404(
        ConferenceSession,
        pk=session_id,
        event=event_form.event,
        is_active=True,
    )
    selected = _selected_submissions(event_form, session).order_by(
        "badge_name",
        "reference_number",
    )
    attendance_by_submission = {
        record.submission_id: record
        for record in session.attendance_records.filter(is_active=True)
        .select_related("checked_in_by")
    }
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response.write("\ufeff")
    response["Content-Disposition"] = (
        f'attachment; filename="{event_form.event.code}-{session.code}-attendance.csv"'
    )
    writer = csv.writer(response)
    writer.writerow([
        _("Reference number"),
        _("Participant"),
        _("Institution"),
        _("Checked in"),
        _("Checked in at"),
        _("Checked in by"),
    ])
    for submission in selected:
        attendance = attendance_by_submission.get(submission.pk)
        writer.writerow([
            safe_spreadsheet_value(submission.reference_number),
            safe_spreadsheet_value(submission.badge_display_name),
            safe_spreadsheet_value(submission.badge_organization),
            _("Yes") if attendance else _("No"),
            attendance.checked_in_at.isoformat() if attendance else "",
            safe_spreadsheet_value(str(attendance.checked_in_by) if attendance else ""),
        ])
    return response


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
