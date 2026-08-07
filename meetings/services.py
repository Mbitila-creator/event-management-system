from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from .models import MeetingCommunicationLog


def _absolute_url(path, request=None):
    if settings.PUBLIC_BASE_URL:
        return f"{settings.PUBLIC_BASE_URL}/{path.lstrip('/')}"
    if request is not None:
        return request.build_absolute_uri(path)
    return path


def _actor(request):
    if request is not None and request.user.is_authenticated:
        return request.user
    return None


def _send_and_log(
    *,
    meeting,
    communication_type,
    recipient_name,
    recipient_email,
    subject,
    body,
    request=None,
    attendee=None,
    action_item=None,
):
    log_values = {
        "meeting": meeting,
        "attendee": attendee,
        "action_item": action_item,
        "communication_type": communication_type,
        "recipient_name": recipient_name,
        "recipient_email": recipient_email,
        "subject": subject,
        "message": body,
        "created_by": _actor(request),
        "updated_by": _actor(request),
    }
    try:
        delivered = send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [recipient_email],
            fail_silently=False,
        )
    except Exception as error:
        MeetingCommunicationLog.objects.create(
            **log_values,
            delivery_status=MeetingCommunicationLog.DeliveryStatus.FAILED,
            error_message=str(error),
        )
        raise
    MeetingCommunicationLog.objects.create(
        **log_values,
        delivery_status=(
            MeetingCommunicationLog.DeliveryStatus.SENT
            if delivered
            else MeetingCommunicationLog.DeliveryStatus.FAILED
        ),
        error_message=(
            "" if delivered else _("The email service did not confirm delivery.")
        ),
    )
    return bool(delivered)


def _meeting_details(meeting, language):
    event = meeting.event
    return {
        "event_name": event.title_en if language == "en" else event.title_sw,
        "meeting_date": date_format(
            timezone.localtime(event.starts_at),
            format="DATETIME_FORMAT",
            use_l10n=True,
        ),
        "venue": str(event.venue) if event.venue else _("To be confirmed"),
    }


def send_meeting_invitation(attendee, request=None):
    """Send one bilingual-ready invitation and return whether it was delivered."""
    recipient = attendee.email.strip()
    if not recipient:
        raise ValueError(_("Enter an email address before sending the invitation."))

    language = attendee.preferred_language
    meeting = attendee.meeting
    with translation.override(language):
        details = _meeting_details(meeting, language)
        event_name = details["event_name"]
        response_path = reverse(
            "meetings:invitation_response",
            kwargs={"response_token": attendee.response_token},
        )
        response_url = _absolute_url(response_path, request=request)
        subject = _("Meeting invitation — %(meeting)s") % {"meeting": event_name}
        body = _(
            "Dear %(name)s,\n\n"
            "You are invited to attend %(meeting)s.\n\n"
            "Reference: %(reference)s\n"
            "Date and time: %(date)s\n"
            "Venue: %(venue)s\n"
            "Chairperson: %(chairperson)s\n\n"
            "Confirm your attendance using this secure link:\n%(response_url)s"
        ) % {
            "name": attendee.full_name,
            "meeting": event_name,
            "reference": meeting.reference_number,
            "date": details["meeting_date"],
            "venue": details["venue"],
            "chairperson": meeting.chairperson_name,
            "response_url": response_url,
        }
        delivered = _send_and_log(
            meeting=meeting,
            attendee=attendee,
            communication_type=MeetingCommunicationLog.CommunicationType.INVITATION,
            recipient_name=attendee.full_name,
            recipient_email=recipient,
            subject=subject,
            body=body,
            request=request,
        )

    if delivered:
        attendee.invitation_sent_at = timezone.now()
        attendee.updated_by = request.user if request and request.user.is_authenticated else None
        attendee.save(update_fields=[
            "invitation_sent_at", "updated_by", "updated_at",
        ])
    return bool(delivered)


def send_rsvp_reminder(attendee, request=None):
    if attendee.response_status in {
        attendee.ResponseStatus.ACCEPTED,
        attendee.ResponseStatus.DECLINED,
    }:
        raise ValueError(_("This participant has already submitted a final response."))
    recipient = attendee.email.strip()
    if not recipient:
        raise ValueError(_("Enter an email address before sending the reminder."))
    language = attendee.preferred_language
    meeting = attendee.meeting
    with translation.override(language):
        details = _meeting_details(meeting, language)
        response_path = reverse(
            "meetings:invitation_response",
            kwargs={"response_token": attendee.response_token},
        )
        response_url = _absolute_url(response_path, request=request)
        subject = _("Reminder: confirm attendance — %(meeting)s") % {
            "meeting": details["event_name"],
        }
        body = _(
            "Dear %(name)s,\n\n"
            "This is a reminder to confirm whether you will attend %(meeting)s.\n\n"
            "Reference: %(reference)s\n"
            "Date and time: %(date)s\n"
            "Venue: %(venue)s\n\n"
            "Submit your response using this secure link:\n%(response_url)s"
        ) % {
            "name": attendee.full_name,
            "meeting": details["event_name"],
            "reference": meeting.reference_number,
            "date": details["meeting_date"],
            "venue": details["venue"],
            "response_url": response_url,
        }
        return _send_and_log(
            meeting=meeting,
            attendee=attendee,
            communication_type=MeetingCommunicationLog.CommunicationType.RSVP_REMINDER,
            recipient_name=attendee.full_name,
            recipient_email=recipient,
            subject=subject,
            body=body,
            request=request,
        )


def send_action_reminder(action, request=None):
    if action.status in {
        action.Status.COMPLETED,
        action.Status.CANCELLED,
    }:
        raise ValueError(_("A reminder cannot be sent for a closed action."))
    recipient = action.responsible_email.strip()
    if not recipient and action.responsible_user_id:
        recipient = action.responsible_user.email.strip()
    if not recipient:
        raise ValueError(_("Enter an email address for the responsible person."))
    language = (
        action.responsible_user.preferred_language
        if action.responsible_user_id
        else "sw"
    )
    meeting = action.meeting
    with translation.override(language):
        details = _meeting_details(meeting, language)
        description = (
            action.description_en
            if language == "en" and action.description_en
            else action.description_sw
        )
        due_date = (
            date_format(action.due_date, format="DATE_FORMAT", use_l10n=True)
            if action.due_date
            else _("Not specified")
        )
        subject = _("Action reminder — %(meeting)s") % {
            "meeting": details["event_name"],
        }
        body = _(
            "Dear %(name)s,\n\n"
            "This is a reminder about an action assigned from %(meeting)s.\n\n"
            "Reference: %(reference)s\n"
            "Action: %(action)s\n"
            "Due date: %(due_date)s\n"
            "Current status: %(status)s\n\n"
            "Please complete the action or provide a progress update."
        ) % {
            "name": action.responsible_name,
            "meeting": details["event_name"],
            "reference": meeting.reference_number,
            "action": description,
            "due_date": due_date,
            "status": action.get_status_display(),
        }
        return _send_and_log(
            meeting=meeting,
            action_item=action,
            communication_type=MeetingCommunicationLog.CommunicationType.ACTION_REMINDER,
            recipient_name=action.responsible_name,
            recipient_email=recipient,
            subject=subject,
            body=body,
            request=request,
        )
