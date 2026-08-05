from django.urls import reverse
from django.utils.translation import gettext as _

from accounts.models import User
from checkin.models import ParticipantCheckIn
from events.models import Event
from forms_builder.models import CertificateRecord, EventForm, FormSubmission, Payment


def administration_dashboard(request):
    """Provide small, permission-aware operational totals to Django Admin."""
    if "/admin/" not in request.path or not request.user.is_authenticated:
        return {}

    cards = []
    if request.user.has_perm("events.view_event"):
        cards.append({
            "label": _("Active events"),
            "value": Event.objects.filter(is_active=True).count(),
            "url": reverse("admin:events_event_changelist"),
            "tone": "blue",
        })

    if request.user.has_perm("forms_builder.view_formsubmission"):
        registration_submissions = FormSubmission.objects.exclude(
            event_form__form_type=EventForm.FormType.EVALUATION,
        ).filter(is_active=True, is_complete=True)
        cards.append({
                "label": _("Pending registrations"),
                "value": registration_submissions.filter(
                    review_status=FormSubmission.ReviewStatus.PENDING,
                ).count(),
                "url": (
                    reverse("admin:forms_builder_participant_changelist")
                    + "?review_status__exact=PENDING"
                ),
                "tone": "gold",
            })
        if request.user.role in {
            User.Role.SYSTEM_ADMIN,
            User.Role.EVENT_ADMIN,
            User.Role.REPORT_OFFICER,
        } or request.user.is_superuser:
            cards.append({
                "label": _("Evaluation responses"),
                "value": FormSubmission.objects.filter(
                    event_form__form_type=EventForm.FormType.EVALUATION,
                    is_active=True,
                    is_complete=True,
                ).count(),
                "url": reverse("forms_builder:evaluation_reports"),
                "tone": "purple",
            })

    if request.user.has_perm("forms_builder.view_payment"):
        cards.append({
            "label": _("Payments awaiting verification"),
            "value": Payment.objects.filter(status=Payment.Status.PENDING).count(),
            "url": (
                reverse("admin:forms_builder_payment_changelist")
                + "?status__exact=PENDING"
            ),
            "tone": "red",
        })

    if request.user.has_perm("checkin.view_participantcheckin"):
        cards.append({
            "label": _("Participants checked in"),
            "value": ParticipantCheckIn.objects.count(),
            "url": reverse("admin:checkin_participantcheckin_changelist"),
            "tone": "green",
        })

    if request.user.has_perm("forms_builder.view_certificaterecord"):
        cards.append({
            "label": _("Certificate eligible"),
            "value": FormSubmission.objects.filter(
                event_form__event__certificate_enabled=True,
                review_status=FormSubmission.ReviewStatus.APPROVED,
                check_in__isnull=False,
                certificate_record__status=CertificateRecord.Status.AUTHORIZED,
                is_active=True,
                is_complete=True,
            ).count(),
            "url": reverse("admin:forms_builder_certificaterecord_changelist"),
            "tone": "navy",
        })

    return {"operational_dashboard_cards": cards}
