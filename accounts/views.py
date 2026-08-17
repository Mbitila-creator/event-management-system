from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .models import User


OPERATIONS_ROLES = {
    User.Role.SYSTEM_ADMIN,
    User.Role.EVENT_ADMIN,
    User.Role.REGISTRATION_OFFICER,
}


def _require_operations_role(user):
    if not (
        user.is_authenticated
        and user.is_active
        and (user.is_superuser or user.role in OPERATIONS_ROLES)
    ):
        raise PermissionDenied


def _require_event_administrator(user):
    if not (
        user.is_authenticated
        and user.is_active
        and (
            user.is_superuser
            or user.role in {User.Role.SYSTEM_ADMIN, User.Role.EVENT_ADMIN}
        )
    ):
        raise PermissionDenied


@login_required(login_url="accounts:staff_login")
def role_home(request):
    """Send each signed-in user to the interface intended for their role."""
    if (
        request.user.is_superuser
        or request.user.role in {
            User.Role.SYSTEM_ADMIN,
            User.Role.DIRECTOR,
            User.Role.ASSISTANT_DIRECTOR,
        }
    ):
        return redirect("admin:index")
    if request.user.role in {
        User.Role.EVENT_ADMIN,
        User.Role.REGISTRATION_OFFICER,
    }:
        from checkin.models import ParticipantCheckIn
        from events.models import Event
        from forms_builder.models import (
            CertificateRecord, EventForm, FormSubmission, Payment,
        )

        submissions = FormSubmission.objects.exclude(
            event_form__form_type=EventForm.FormType.EVALUATION,
        ).filter(is_active=True, is_complete=True).select_related(
            "event_form__event",
        )
        pending_submissions = submissions.filter(
            review_status=FormSubmission.ReviewStatus.PENDING,
        )
        pending_payments = Payment.objects.filter(
            status=Payment.Status.PENDING,
        ).select_related("submission", "submission__event_form__event")
        certificate_candidates = submissions.filter(
            review_status=FormSubmission.ReviewStatus.APPROVED,
            event_form__event__certificate_enabled=True,
            check_in__isnull=False,
        ).select_related("certificate_record").order_by("-created_at")
        selected_view = request.GET.get("view", "all")
        if selected_view not in {
            "all", "events", "registrations", "payments", "checkins",
        }:
            selected_view = "all"
        active_event_rows = Event.objects.filter(is_active=True).select_related(
            "venue",
        ).order_by("starts_at")
        checked_in_rows = ParticipantCheckIn.objects.select_related(
            "submission__event_form__event", "checked_in_by",
        ).order_by("-checked_in_at")
        return render(request, "accounts/staff_workspace.html", {
            "active_events": active_event_rows.count(),
            "pending_registration_count": pending_submissions.count(),
            "pending_payment_count": pending_payments.count(),
            "checked_in_count": ParticipantCheckIn.objects.count(),
            "active_event_rows": active_event_rows,
            "checked_in_rows": checked_in_rows,
            "selected_view": selected_view,
            "recent_submissions": pending_submissions.order_by(
                "-created_at",
            )[:8],
            "recent_payments": pending_payments.order_by("-created_at")[:8],
            "certificate_candidates": certificate_candidates[:8],
            "certificate_candidate_count": certificate_candidates.filter(
                certificate_record__isnull=True,
            ).count(),
            "is_event_admin": request.user.role == User.Role.EVENT_ADMIN,
        })
    if request.user.role == User.Role.ATTENDANCE_OFFICER:
        return redirect("checkin:lookup")
    if request.user.role == User.Role.REPORT_OFFICER:
        return redirect("checkin:reports")
    if request.user.role == User.Role.PARTICIPANT:
        from meetings.models import MeetingActionItem, MeetingAttendee

        has_meeting_work = (
            MeetingAttendee.objects.filter(
                user=request.user,
                is_active=True,
                meeting__is_active=True,
            ).exists()
            or MeetingActionItem.objects.filter(
                responsible_user=request.user,
                is_active=True,
                meeting__is_active=True,
            ).exists()
        )
        if has_meeting_work:
            return redirect("meetings:personal_meeting_workspace")
    return redirect("forms_builder:registration_status")


@login_required(login_url="accounts:staff_login")
def participant_review_details(request, submission_id):
    """Show the complete evidence needed for registration and payment decisions."""
    from forms_builder.models import EventForm, FormSubmission

    _require_operations_role(request.user)
    submission = get_object_or_404(
        FormSubmission.objects.exclude(
            event_form__form_type=EventForm.FormType.EVALUATION,
        ).select_related(
            "event_form__event",
            "reviewed_by",
        ).prefetch_related(
            "answers__question__section",
            "answers__selected_options",
            "payments",
        ),
        pk=submission_id,
        is_active=True,
        is_complete=True,
    )
    language = request.LANGUAGE_CODE
    sections = []
    section_lookup = {}
    for answer in submission.answers.all():
        question = answer.question
        section = question.section
        section_id = section.pk
        if section_id not in section_lookup:
            section_data = {
                "title": section.title_en if language == "en" else section.title_sw,
                "answers": [],
            }
            section_lookup[section_id] = section_data
            sections.append(section_data)
        selected_options = list(answer.selected_options.all())
        if selected_options:
            value = ", ".join(
                option.label_en if language == "en" else option.label_sw
                for option in selected_options
            )
        elif answer.uploaded_file:
            value = answer.uploaded_file.name.rsplit("/", 1)[-1]
        elif answer.text_value:
            value = answer.text_value
        elif answer.number_value is not None:
            value = str(answer.number_value)
        elif answer.date_value:
            value = answer.date_value.isoformat()
        elif answer.datetime_value:
            value = answer.datetime_value.strftime("%d %b %Y, %H:%M")
        elif answer.boolean_value is not None:
            value = _("Yes") if answer.boolean_value else _("No")
        else:
            value = "—"
        section_lookup[section_id]["answers"].append({
            "label": question.label_en if language == "en" else question.label_sw,
            "value": value,
            "file_url": answer.uploaded_file.url if answer.uploaded_file else "",
        })
    return render(request, "accounts/participant_review_details.html", {
        "submission": submission,
        "event": submission.event_form.event,
        "sections": sections,
        "payments": submission.payments.all().order_by("-created_at"),
    })


@login_required(login_url="accounts:staff_login")
def booth_assignments(request):
    from events.models import Event
    from forms_builder.models import Booth, EventForm, FormSubmission

    _require_event_administrator(request.user)
    events = Event.objects.filter(
        is_active=True,
        booth_enabled=True,
    ).order_by("starts_at")
    selected_event = None
    event_id = request.GET.get("event")
    if event_id:
        selected_event = events.filter(pk=event_id).first()
    if selected_event is None:
        selected_event = events.first()

    booths = []
    if selected_event:
        booths = list(Booth.objects.filter(
            event=selected_event,
            is_active=True,
        ).select_related("assigned_submission").order_by("zone_en", "code"))
        eligible = FormSubmission.objects.filter(
            event_form__event=selected_event,
            event_form__form_type__in={
                EventForm.FormType.REGISTRATION,
                EventForm.FormType.EXHIBITOR,
            },
            review_status=FormSubmission.ReviewStatus.APPROVED,
            is_active=True,
            is_complete=True,
        ).select_related("event_form").order_by("badge_organization", "badge_name")
        for booth in booths:
            booth.eligible_submissions = eligible.filter(
                Q(booth_assignment__isnull=True) | Q(booth_assignment=booth)
            )
    return render(request, "accounts/booth_assignments.html", {
        "events": events,
        "selected_event": selected_event,
        "booths": booths,
    })


@login_required(login_url="accounts:staff_login")
@require_POST
def update_booth_assignment(request, booth_id):
    from forms_builder.models import Booth, EventForm, FormSubmission

    _require_event_administrator(request.user)
    action = request.POST.get("action", "")
    try:
        with transaction.atomic():
            booth = get_object_or_404(
                Booth.objects.select_for_update().select_related("event"),
                pk=booth_id,
                is_active=True,
                event__booth_enabled=True,
            )
            if action == "assign":
                submission = get_object_or_404(
                    FormSubmission.objects.filter(
                        Q(booth_assignment__isnull=True)
                        | Q(booth_assignment=booth),
                        event_form__event=booth.event,
                        event_form__form_type__in={
                            EventForm.FormType.REGISTRATION,
                            EventForm.FormType.EXHIBITOR,
                        },
                        review_status=FormSubmission.ReviewStatus.APPROVED,
                        is_active=True,
                        is_complete=True,
                    ),
                    pk=request.POST.get("submission_id"),
                )
                booth.assigned_submission = submission
                booth.status = Booth.Status.ASSIGNED
                success_message = _("Booth assigned successfully.")
            elif action == "ready":
                if not booth.assigned_submission_id:
                    messages.error(request, _("Assign an exhibitor before marking the booth ready."))
                    return redirect("accounts:booth_assignments")
                booth.status = Booth.Status.READY
                success_message = _("Booth marked as ready.")
            elif action == "release":
                booth.assigned_submission = None
                booth.status = Booth.Status.UNASSIGNED
                success_message = _("Booth assignment released.")
            else:
                raise PermissionDenied
            booth.updated_by = request.user
            booth.save()
    except IntegrityError:
        messages.error(
            request,
            _("This exhibitor is already assigned to another booth."),
        )
        return redirect("accounts:booth_assignments")
    messages.success(request, success_message)
    return redirect(f"{reverse('accounts:booth_assignments')}?event={booth.event_id}")


@require_POST
def staff_logout(request):
    logout(request)
    return redirect("accounts:staff_login")


@login_required(login_url="accounts:staff_login")
@require_POST
def review_registration(request, submission_id, decision):
    from forms_builder.models import EventForm, FormSubmission, NotificationLog
    from forms_builder.notifications import send_submission_notification

    _require_operations_role(request.user)
    statuses = {
        "approve": FormSubmission.ReviewStatus.APPROVED,
        "reject": FormSubmission.ReviewStatus.REJECTED,
    }
    status = statuses.get(decision)
    if status is None:
        raise PermissionDenied
    submission = get_object_or_404(
        FormSubmission.objects.exclude(
            event_form__form_type=EventForm.FormType.EVALUATION,
        ),
        pk=submission_id,
        is_active=True,
        is_complete=True,
    )
    reason = request.POST.get("reason", "").strip()
    if status == FormSubmission.ReviewStatus.REJECTED and not reason:
        messages.error(request, _("Enter a reason before rejecting the registration."))
        return redirect("accounts:role_home")
    submission.review_status = status
    submission.reviewed_by = request.user
    submission.reviewed_at = timezone.now()
    submission.updated_by = request.user
    if status == FormSubmission.ReviewStatus.REJECTED:
        submission.review_notes = reason
    submission.save(update_fields=(
        "review_status", "reviewed_by", "reviewed_at", "updated_by",
        "review_notes", "updated_at",
    ))
    notification_type = (
        NotificationLog.NotificationType.REGISTRATION_APPROVED
        if status == FormSubmission.ReviewStatus.APPROVED
        else NotificationLog.NotificationType.REGISTRATION_REJECTED
    )
    send_submission_notification(submission, notification_type, request=request)
    return redirect("accounts:role_home")


@login_required(login_url="accounts:staff_login")
@require_POST
def review_payment(request, payment_id, decision):
    from forms_builder.models import NotificationLog, Payment
    from forms_builder.notifications import send_payment_notification

    _require_operations_role(request.user)
    statuses = {
        "verify": Payment.Status.VERIFIED,
        "reject": Payment.Status.REJECTED,
    }
    status = statuses.get(decision)
    if status is None:
        raise PermissionDenied
    payment = get_object_or_404(Payment, pk=payment_id)
    reason = request.POST.get("reason", "").strip()
    if status == Payment.Status.REJECTED and not reason:
        messages.error(request, _("Enter a reason before rejecting the payment."))
        return redirect("accounts:role_home")
    payment.status = status
    payment.verified_by = request.user if status == Payment.Status.VERIFIED else None
    payment.verified_at = timezone.now() if status == Payment.Status.VERIFIED else None
    payment.updated_by = request.user
    if status == Payment.Status.REJECTED:
        payment.notes = reason
    payment.save(update_fields=(
        "status", "verified_by", "verified_at", "notes", "updated_by",
        "updated_at",
    ))
    notification_type = (
        NotificationLog.NotificationType.PAYMENT_VERIFIED
        if status == Payment.Status.VERIFIED
        else NotificationLog.NotificationType.PAYMENT_REJECTED
    )
    send_payment_notification(payment, notification_type, request=request)
    messages.success(request, _("Payment status updated successfully."))
    return redirect("accounts:role_home")


@login_required(login_url="accounts:staff_login")
@require_POST
def update_certificate_authorization(request, submission_id, decision):
    from forms_builder.models import CertificateRecord, FormSubmission, NotificationLog
    from forms_builder.notifications import send_submission_notification
    from forms_builder.services import certificate_number

    _require_event_administrator(request.user)
    submission = get_object_or_404(
        FormSubmission.objects.filter(
            review_status=FormSubmission.ReviewStatus.APPROVED,
            event_form__event__certificate_enabled=True,
            check_in__isnull=False,
        ),
        pk=submission_id,
    )
    now = timezone.now()
    reason = request.POST.get("reason", "").strip()
    if decision == "authorize":
        certificate, created = CertificateRecord.objects.get_or_create(
            submission=submission,
            defaults={
                "certificate_number": certificate_number(submission),
                "status": CertificateRecord.Status.AUTHORIZED,
                "authorized_by": request.user,
                "authorized_at": now,
                "denied_by": None,
                "denied_at": None,
                "denial_reason": "",
                "created_by": request.user,
                "updated_by": request.user,
            },
        )
        if not created:
            certificate.certificate_number = certificate_number(submission)
            certificate.status = CertificateRecord.Status.AUTHORIZED
            certificate.authorized_by = request.user
            certificate.authorized_at = now
            certificate.revoked_by = None
            certificate.revoked_at = None
            certificate.revocation_reason = ""
            certificate.denied_by = None
            certificate.denied_at = None
            certificate.denial_reason = ""
            certificate.updated_by = request.user
            certificate.save()
        send_submission_notification(
            submission,
            NotificationLog.NotificationType.CERTIFICATE_AUTHORIZED,
            request=request,
        )
        messages.success(request, _("Certificate authorized successfully."))
    elif decision == "deny":
        if not reason:
            messages.error(request, _("Enter a reason for not authorizing the certificate."))
            return redirect("accounts:role_home")
        certificate, created = CertificateRecord.objects.get_or_create(
            submission=submission,
            defaults={
                "certificate_number": certificate_number(submission),
                "status": CertificateRecord.Status.DENIED,
                "authorized_by": None,
                "authorized_at": None,
                "denied_by": request.user,
                "denied_at": now,
                "denial_reason": reason,
                "created_by": request.user,
                "updated_by": request.user,
            },
        )
        if not created:
            certificate.status = CertificateRecord.Status.DENIED
            certificate.authorized_by = None
            certificate.authorized_at = None
            certificate.denied_by = request.user
            certificate.denied_at = now
            certificate.denial_reason = reason
            certificate.revoked_by = None
            certificate.revoked_at = None
            certificate.revocation_reason = ""
            certificate.updated_by = request.user
            certificate.save()
        send_submission_notification(
            submission,
            NotificationLog.NotificationType.CERTIFICATE_DENIED,
            request=request,
        )
        messages.success(request, _("Certificate decision recorded successfully."))
    elif decision == "revoke":
        if not reason:
            messages.error(request, _("Enter a reason before revoking the certificate."))
            return redirect("accounts:role_home")
        certificate = get_object_or_404(
            CertificateRecord,
            submission=submission,
            status=CertificateRecord.Status.AUTHORIZED,
        )
        certificate.status = CertificateRecord.Status.REVOKED
        certificate.revoked_by = request.user
        certificate.revoked_at = now
        certificate.revocation_reason = reason
        certificate.updated_by = request.user
        certificate.save(update_fields=(
            "status", "revoked_by", "revoked_at", "revocation_reason",
            "updated_by", "updated_at",
        ))
        messages.success(request, _("Certificate authorization revoked."))
    else:
        raise PermissionDenied
    return redirect("accounts:role_home")
