import uuid

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
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


class ConferenceSpeaker(BaseModel):
    event = models.ForeignKey(
        Event,
        related_name="conference_speakers",
        on_delete=models.CASCADE,
        verbose_name=_("conference event"),
    )
    full_name = models.CharField(_("full name"), max_length=200)
    position_title = models.CharField(_("position / title"), max_length=200, blank=True)
    institution = models.CharField(_("institution"), max_length=250, blank=True)
    biography = models.TextField(_("short biography"), blank=True)
    photo = models.ImageField(
        _("photo"),
        upload_to="conferences/speakers/",
        blank=True,
        null=True,
    )
    display_order = models.PositiveIntegerField(_("display order"), default=0)

    class Meta:
        ordering = ("display_order", "full_name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("event", "full_name", "institution"),
                name="unique_conference_speaker_per_event",
            ),
        ]

    def clean(self):
        if self.event_id and not self.event.category.is_conference:
            raise ValidationError({
                "event": _("Select an event in the Conference category."),
            })

    def save(self, *args, **kwargs):
        self.full_name = self.full_name.strip()
        self.position_title = self.position_title.strip()
        self.institution = self.institution.strip()
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.full_name


class ConferenceProgrammeItem(BaseModel):
    class ItemType(models.TextChoices):
        OPENING = "OPENING", _("Opening")
        KEYNOTE = "KEYNOTE", _("Keynote address")
        PRESENTATION = "PRESENTATION", _("Presentation")
        PANEL = "PANEL", _("Panel discussion")
        WORKSHOP = "WORKSHOP", _("Workshop")
        BREAK = "BREAK", _("Break")
        NETWORKING = "NETWORKING", _("Networking")
        CLOSING = "CLOSING", _("Closing")
        OTHER = "OTHER", _("Other")

    session = models.ForeignKey(
        ConferenceSession,
        related_name="programme_items",
        on_delete=models.CASCADE,
        verbose_name=_("conference session"),
    )
    code = models.CharField(_("programme item code"), max_length=80)
    item_type = models.CharField(
        _("programme item type"),
        max_length=20,
        choices=ItemType.choices,
        default=ItemType.PRESENTATION,
    )
    title = models.CharField(_("programme title"), max_length=300)
    description = models.TextField(_("description"), blank=True)
    starts_at = models.DateTimeField(_("programme item starts"))
    ends_at = models.DateTimeField(_("programme item ends"))
    venue_name = models.CharField(_("venue"), max_length=250, blank=True)
    is_published = models.BooleanField(_("published"), default=False)
    display_order = models.PositiveIntegerField(_("display order"), default=0)
    speakers = models.ManyToManyField(
        ConferenceSpeaker,
        related_name="programme_items",
        through="ConferenceProgrammeContributor",
        blank=True,
        verbose_name=_("speakers and facilitators"),
    )

    class Meta:
        ordering = ("starts_at", "display_order", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("session", "code"),
                name="unique_programme_item_code_per_session",
            ),
        ]

    def clean(self):
        errors = {}
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            errors["ends_at"] = _("The programme item must end after it starts.")
        if self.session_id and self.starts_at and self.starts_at < self.session.starts_at:
            errors["starts_at"] = _("The programme item cannot start before its session.")
        if self.session_id and self.ends_at and self.ends_at > self.session.ends_at:
            errors["ends_at"] = _("The programme item cannot end after its session.")
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        self.title = self.title.strip()
        if not self.venue_name and self.session_id:
            self.venue_name = self.session.venue_name
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.session.code} — {self.title}"


class ConferenceProgrammeContributor(BaseModel):
    class Role(models.TextChoices):
        SPEAKER = "SPEAKER", _("Speaker")
        KEYNOTE_SPEAKER = "KEYNOTE_SPEAKER", _("Keynote speaker")
        MODERATOR = "MODERATOR", _("Moderator")
        PANELIST = "PANELIST", _("Panelist")
        FACILITATOR = "FACILITATOR", _("Facilitator")

    programme_item = models.ForeignKey(
        ConferenceProgrammeItem,
        related_name="contributors",
        on_delete=models.CASCADE,
        verbose_name=_("programme item"),
    )
    speaker = models.ForeignKey(
        ConferenceSpeaker,
        related_name="programme_contributions",
        on_delete=models.CASCADE,
        verbose_name=_("speaker / facilitator"),
    )
    role = models.CharField(
        _("programme role"),
        max_length=30,
        choices=Role.choices,
        default=Role.SPEAKER,
    )
    display_order = models.PositiveIntegerField(_("display order"), default=0)

    class Meta:
        ordering = ("display_order", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("programme_item", "speaker", "role"),
                name="unique_contributor_role_per_programme_item",
            ),
        ]

    def clean(self):
        if (
            self.programme_item_id
            and self.speaker_id
            and self.programme_item.session.event_id != self.speaker.event_id
        ):
            raise ValidationError({
                "speaker": _("The contributor belongs to another conference."),
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.speaker} — {self.get_role_display()}"


class ConferenceCallForPapers(BaseModel):
    event = models.OneToOneField(
        Event,
        related_name="conference_call_for_papers",
        on_delete=models.CASCADE,
        verbose_name=_("conference event"),
    )
    title = models.CharField(_("call title"), max_length=250)
    introduction = models.TextField(_("introduction"))
    guidelines = models.TextField(_("submission guidelines"))
    opens_at = models.DateTimeField(_("opens at"), null=True, blank=True)
    closes_at = models.DateTimeField(_("closes at"), null=True, blank=True)
    is_published = models.BooleanField(_("published"), default=False)

    class Meta:
        verbose_name = _("conference call for papers")
        verbose_name_plural = _("conference calls for papers")

    def clean(self):
        errors = {}
        if self.event_id and not self.event.category.is_conference:
            errors["event"] = _("Select an event in the Conference category.")
        if self.opens_at and self.closes_at and self.closes_at <= self.opens_at:
            errors["closes_at"] = _("The closing time must be after the opening time.")
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.event.code} — {self.title}"


class ConferencePaper(BaseModel):
    class SubmissionType(models.TextChoices):
        ABSTRACT = "ABSTRACT", _("Abstract")
        FULL_PAPER = "FULL_PAPER", _("Full paper")

    class PresentationFormat(models.TextChoices):
        ORAL = "ORAL", _("Oral presentation")
        POSTER = "POSTER", _("Poster presentation")
        PANEL = "PANEL", _("Panel contribution")
        WORKSHOP = "WORKSHOP", _("Workshop contribution")

    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", _("Submitted")
        UNDER_REVIEW = "UNDER_REVIEW", _("Under review")
        REVISION_REQUIRED = "REVISION_REQUIRED", _("Revision required")
        ACCEPTED = "ACCEPTED", _("Accepted")
        REJECTED = "REJECTED", _("Rejected")
        WITHDRAWN = "WITHDRAWN", _("Withdrawn")

    call = models.ForeignKey(
        ConferenceCallForPapers,
        related_name="papers",
        on_delete=models.CASCADE,
        verbose_name=_("call for papers"),
    )
    public_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    reference_number = models.CharField(
        _("reference number"), max_length=80, unique=True, null=True, blank=True,
    )
    submission_type = models.CharField(
        _("submission type"), max_length=20, choices=SubmissionType.choices,
        default=SubmissionType.ABSTRACT,
    )
    presentation_format = models.CharField(
        _("preferred presentation format"), max_length=20,
        choices=PresentationFormat.choices, default=PresentationFormat.ORAL,
    )
    title = models.CharField(_("research / paper title"), max_length=400)
    abstract = models.TextField(_("abstract"))
    thematic_area = models.CharField(_("thematic area"), max_length=250)
    keywords = models.CharField(_("keywords"), max_length=400, blank=True)
    corresponding_author = models.CharField(_("corresponding author"), max_length=200)
    institution = models.CharField(_("institution"), max_length=250)
    email = models.EmailField(_("email address"))
    phone = models.CharField(_("phone number"), max_length=40)
    co_authors = models.TextField(
        _("co-authors"), blank=True,
        help_text=_("Enter one co-author per line, including institution where applicable."),
    )
    document = models.FileField(
        _("abstract or paper document"), upload_to="conferences/papers/%Y/%m/",
        blank=True, null=True,
        validators=[FileExtensionValidator(("pdf", "doc", "docx"))],
    )
    status = models.CharField(
        _("review status"), max_length=30, choices=Status.choices,
        default=Status.SUBMITTED,
    )
    assigned_session = models.ForeignKey(
        ConferenceSession, related_name="accepted_papers", on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name=_("assigned conference session"),
    )
    decision_message = models.TextField(_("message to the author"), blank=True)
    internal_notes = models.TextField(_("internal review notes"), blank=True)
    reviewed_by = models.ForeignKey(
        "accounts.User", related_name="reviewed_conference_papers",
        on_delete=models.SET_NULL, null=True, blank=True, editable=False,
        verbose_name=_("reviewed by"),
    )
    reviewed_at = models.DateTimeField(_("reviewed at"), null=True, blank=True, editable=False)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("call", "email", "title"),
                name="unique_conference_paper_title_per_author",
            ),
        ]

    def clean(self):
        errors = {}
        if (
            self.assigned_session_id
            and self.call_id
            and self.assigned_session.event_id != self.call.event_id
        ):
            errors["assigned_session"] = _("Select a session from the same conference.")
        uploaded_file = getattr(self.document, "_file", None)
        if uploaded_file and uploaded_file.size > 10 * 1024 * 1024:
            errors["document"] = _("The uploaded document must not exceed 10 MB.")
        if self.submission_type == self.SubmissionType.FULL_PAPER and not self.document:
            errors["document"] = _("Upload the document when submitting a full paper.")
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.title = self.title.strip()
        self.corresponding_author = self.corresponding_author.strip()
        self.institution = self.institution.strip()
        self.email = self.email.strip().lower()
        self.full_clean()
        super().save(*args, **kwargs)
        if not self.reference_number:
            reference = f"{self.call.event.code}-ABS-{self.pk:05d}"
            type(self).objects.filter(pk=self.pk).update(reference_number=reference)
            self.reference_number = reference

    def __str__(self):
        return f"{self.reference_number or 'New'} — {self.title}"


class ConferencePaperReview(BaseModel):
    paper = models.ForeignKey(
        ConferencePaper, related_name="review_history", on_delete=models.CASCADE,
        verbose_name=_("conference paper"),
    )
    decision = models.CharField(
        _("decision"), max_length=30, choices=ConferencePaper.Status.choices,
    )
    message_to_author = models.TextField(_("message to the author"), blank=True)
    internal_notes = models.TextField(_("internal notes"), blank=True)
    assigned_session = models.ForeignKey(
        ConferenceSession, related_name="paper_review_assignments",
        on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name=_("assigned conference session"),
    )
    reviewer = models.ForeignKey(
        "accounts.User", related_name="conference_paper_reviews",
        on_delete=models.PROTECT, verbose_name=_("reviewer"),
    )

    class Meta:
        ordering = ("-created_at",)

    def clean(self):
        if (
            self.assigned_session_id
            and self.paper_id
            and self.assigned_session.event_id != self.paper.call.event_id
        ):
            raise ValidationError({
                "assigned_session": _("Select a session from the same conference."),
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.paper.reference_number} — {self.get_decision_display()}"
