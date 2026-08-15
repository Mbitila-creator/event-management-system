from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel
from events.models import Event
from forms_builder.models import FormSubmission


class ConferenceSession(BaseModel):
    event = models.ForeignKey(
        Event,
        related_name="conference_sessions",
        on_delete=models.CASCADE,
        verbose_name=_("conference event"),
    )
    code = models.CharField(_("session code"), max_length=80)
    title = models.CharField(_("session title"), max_length=300)
    starts_at = models.DateTimeField(_("session starts"))
    ends_at = models.DateTimeField(_("session ends"))
    venue_name = models.CharField(_("session venue"), max_length=250, blank=True)
    registration_option_value = models.CharField(
        _("registration option value"),
        max_length=100,
        help_text=_("Stored value of the matching registration-form option."),
    )
    display_order = models.PositiveIntegerField(_("display order"), default=0)

    class Meta:
        ordering = ("starts_at", "display_order", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("event", "code"),
                name="unique_conference_session_code_per_event",
            ),
            models.UniqueConstraint(
                fields=("event", "registration_option_value"),
                name="unique_conference_session_option_per_event",
            ),
        ]

    def clean(self):
        errors = {}
        if self.event_id and not self.event.category.is_conference:
            errors["event"] = _("Select an event in the Conference category.")
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            errors["ends_at"] = _("The session must end after it starts.")
        if self.event_id and self.starts_at and self.starts_at < self.event.starts_at:
            errors["starts_at"] = _("The session cannot start before the conference.")
        if self.event_id and self.ends_at and self.ends_at > self.event.ends_at:
            errors["ends_at"] = _("The session cannot end after the conference.")
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        self.registration_option_value = self.registration_option_value.strip()
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.event.code} — {self.title}"


class ConferenceSessionAttendance(BaseModel):
    class Method(models.TextChoices):
        QR = "QR", _("QR code")
        MANUAL = "MANUAL", _("Manual lookup")

    session = models.ForeignKey(
        ConferenceSession,
        related_name="attendance_records",
        on_delete=models.CASCADE,
        verbose_name=_("conference session"),
    )
    submission = models.ForeignKey(
        FormSubmission,
        related_name="conference_session_attendance",
        on_delete=models.CASCADE,
        verbose_name=_("participant registration"),
    )
    checked_in_at = models.DateTimeField(_("checked in at"), auto_now_add=True)
    checked_in_by = models.ForeignKey(
        "accounts.User",
        related_name="conference_session_checkins",
        on_delete=models.PROTECT,
        verbose_name=_("checked in by"),
    )
    method = models.CharField(
        _("check-in method"),
        max_length=20,
        choices=Method.choices,
        default=Method.QR,
    )

    class Meta:
        ordering = ("-checked_in_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("session", "submission"),
                name="unique_participant_checkin_per_conference_session",
            ),
        ]

    def clean(self):
        errors = {}
        if (
            self.session_id
            and self.submission_id
            and self.submission.event_form.event_id != self.session.event_id
        ):
            errors["submission"] = _(
                "The participant registration belongs to another event."
            )
        if (
            self.submission_id
            and self.submission.review_status
            != FormSubmission.ReviewStatus.APPROVED
        ):
            errors["submission"] = _("Only approved participants may check in.")
        if (
            self.session_id
            and self.submission_id
            and not self.submission.answers.filter(
                question__section__event_form=self.submission.event_form,
                selected_options__value=self.session.registration_option_value,
                selected_options__is_active=True,
            ).exists()
        ):
            errors["submission"] = _("The participant did not select this session.")
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.session.code} — {self.submission.reference_number}"
