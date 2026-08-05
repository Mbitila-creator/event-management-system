from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .models import User


@login_required(login_url="accounts:staff_login")
def role_home(request):
    """Send each signed-in user to the interface intended for their role."""
    if request.user.is_superuser or request.user.role == User.Role.SYSTEM_ADMIN:
        return redirect("admin:index")
    if request.user.role in {
        User.Role.EVENT_ADMIN,
        User.Role.REGISTRATION_OFFICER,
    }:
        from checkin.models import ParticipantCheckIn
        from events.models import Event
        from forms_builder.models import EventForm, FormSubmission, Payment

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
        return render(request, "accounts/staff_workspace.html", {
            "active_events": Event.objects.filter(is_active=True).count(),
            "pending_registration_count": pending_submissions.count(),
            "pending_payment_count": pending_payments.count(),
            "checked_in_count": ParticipantCheckIn.objects.count(),
            "recent_submissions": pending_submissions.order_by(
                "-created_at",
            )[:8],
            "recent_payments": pending_payments.order_by("-created_at")[:8],
            "is_event_admin": request.user.role == User.Role.EVENT_ADMIN,
        })
    if request.user.role == User.Role.ATTENDANCE_OFFICER:
        return redirect("checkin:lookup")
    if request.user.role == User.Role.REPORT_OFFICER:
        return redirect("checkin:reports")
    return redirect("forms_builder:registration_status")


@require_POST
def staff_logout(request):
    logout(request)
    return redirect("accounts:staff_login")
