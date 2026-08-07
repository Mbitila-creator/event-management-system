from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.formats import date_format
from django.utils.translation import gettext as _


def _absolute_url(path, request=None):
    if settings.PUBLIC_BASE_URL:
        return f"{settings.PUBLIC_BASE_URL}/{path.lstrip('/')}"
    if request is not None:
        return request.build_absolute_uri(path)
    return path


def send_meeting_invitation(attendee, request=None):
    """Send one bilingual-ready invitation and return whether it was delivered."""
    recipient = attendee.email.strip()
    if not recipient:
        raise ValueError(_("Enter an email address before sending the invitation."))

    language = attendee.preferred_language
    meeting = attendee.meeting
    event = meeting.event
    with translation.override(language):
        event_name = event.title_en if language == "en" else event.title_sw
        response_path = reverse(
            "meetings:invitation_response",
            kwargs={"response_token": attendee.response_token},
        )
        response_url = _absolute_url(response_path, request=request)
        meeting_date = date_format(
            timezone.localtime(event.starts_at),
            format="DATETIME_FORMAT",
            use_l10n=True,
        )
        venue = str(event.venue) if event.venue else _("To be confirmed")
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
            "date": meeting_date,
            "venue": venue,
            "chairperson": meeting.chairperson_name,
            "response_url": response_url,
        }
        delivered = send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
            fail_silently=False,
        )

    if delivered:
        attendee.invitation_sent_at = timezone.now()
        attendee.updated_by = request.user if request and request.user.is_authenticated else None
        attendee.save(update_fields=[
            "invitation_sent_at", "updated_by", "updated_at",
        ])
    return bool(delivered)
