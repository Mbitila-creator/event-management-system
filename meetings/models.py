import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel
from events.models import Event


class Meeting(BaseModel):
    """Meeting-specific configuration attached to the shared event record."""

    class MeetingType(models.TextChoices):
        MANAGEMENT = "MANAGEMENT", _("Management meeting")
        TECHNICAL = "TECHNICAL", _("Technical meeting")
        COMMITTEE = "COMMITTEE", _("Committee meeting")
        BOARD = "BOARD", _("Board meeting")
        STAKEHOLDER = "STAKEHOLDER", _("Stakeholder meeting")
        WORKING_SESSION = "WORKING_SESSION", _("Working session")
        OTHER = "OTHER", _("Other meeting")

    class MinutesStatus(models.TextChoices):
        NOT_STARTED = "NOT_STARTED", _("Not started")
        DRAFT = "DRAFT", _("Draft")
        SUBMITTED = "SUBMITTED", _("Submitted for approval")
        APPROVED = "APPROVED", _("Approved")

    event = models.OneToOneField(
        Event,
        verbose_name=_("event"),
        related_name="meeting",
        on_delete=models.CASCADE,
    )
    reference_number = models.CharField(
        _("meeting reference number"),
        max_length=80,
        unique=True,
        help_text=_("Use the official meeting reference when available."),
    )
    meeting_type = models.CharField(
        _("meeting type"),
        max_length=30,
        choices=MeetingType.choices,
        default=MeetingType.MANAGEMENT,
    )
    chairperson_name = models.CharField(
        _("chairperson"),
        max_length=200,
    )
    secretary_name = models.CharField(
        _("meeting secretary"),
        max_length=200,
        blank=True,
    )
    quorum_required = models.PositiveIntegerField(
        _("required quorum"),
        null=True,
        blank=True,
        help_text=_("Leave empty when the meeting has no formal quorum."),
    )
    invitation_deadline = models.DateTimeField(
        _("invitation response deadline"),
        null=True,
        blank=True,
    )
    objectives_sw = models.TextField(
        _("objectives in Kiswahili"),
        blank=True,
    )
    objectives_en = models.TextField(
        _("objectives in English"),
        blank=True,
    )
    minutes_status = models.CharField(
        _("minutes status"),
        max_length=20,
        choices=MinutesStatus.choices,
        default=MinutesStatus.NOT_STARTED,
    )
    minutes_sw = models.TextField(
        _("minutes in Kiswahili"),
        blank=True,
    )
    minutes_en = models.TextField(
        _("minutes in English"),
        blank=True,
    )
    minutes_document = models.FileField(
        _("signed minutes document"),
        upload_to="meetings/minutes/%Y/%m/",
        null=True,
        blank=True,
    )
    minutes_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("minutes approved by"),
        related_name="approved_meeting_minutes",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    minutes_approved_at = models.DateTimeField(
        _("minutes approved at"),
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = _("meeting")
        verbose_name_plural = _("meetings")
        ordering = ["-event__starts_at", "reference_number"]
        indexes = [
            models.Index(
                fields=["meeting_type", "minutes_status"],
                name="meeting_type_minutes_idx",
            ),
        ]

    def clean(self):
        errors = {}
        if self.event_id and self.event.category.code.upper() != "MEETING":
            errors["event"] = _(
                "Only an event in the MEETING category can have meeting details."
            )
        if (
            self.invitation_deadline
            and self.event_id
            and self.invitation_deadline > self.event.starts_at
        ):
            errors["invitation_deadline"] = _(
                "The invitation deadline cannot be after the meeting starts."
            )
        if self.quorum_required == 0:
            errors["quorum_required"] = _(
                "The required quorum must be greater than zero."
            )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.reference_number = self.reference_number.strip().upper()
        if (
            self.minutes_status == self.MinutesStatus.APPROVED
            and not self.minutes_approved_at
        ):
            self.minutes_approved_at = timezone.now()
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.reference_number} - {self.event.title_sw}"

    def get_absolute_url(self):
        return reverse("meetings:meeting_detail", kwargs={"meeting_id": self.pk})


class MeetingAgendaItem(BaseModel):
    meeting = models.ForeignKey(
        Meeting,
        verbose_name=_("meeting"),
        related_name="agenda_items",
        on_delete=models.CASCADE,
    )
    item_number = models.PositiveIntegerField(_("agenda item number"))
    title_sw = models.CharField(
        _("agenda title in Kiswahili"),
        max_length=300,
    )
    title_en = models.CharField(
        _("agenda title in English"),
        max_length=300,
    )
    presenter_name = models.CharField(
        _("presenter"),
        max_length=200,
        blank=True,
    )
    allocated_minutes = models.PositiveIntegerField(
        _("allocated minutes"),
        null=True,
        blank=True,
    )
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        verbose_name = _("meeting agenda item")
        verbose_name_plural = _("meeting agenda items")
        ordering = ["meeting", "item_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["meeting", "item_number"],
                name="unique_agenda_number_per_meeting",
            ),
        ]

    def __str__(self):
        return f"{self.meeting.reference_number} - {self.item_number}. {self.title_sw}"


class MeetingAttendee(BaseModel):
    class AttendeeType(models.TextChoices):
        INTERNAL = "INTERNAL", _("Internal participant")
        EXTERNAL = "EXTERNAL", _("External participant")

    class ResponseStatus(models.TextChoices):
        INVITED = "INVITED", _("Invited")
        ACCEPTED = "ACCEPTED", _("Accepted")
        DECLINED = "DECLINED", _("Declined")
        TENTATIVE = "TENTATIVE", _("Tentative")

    class AttendanceStatus(models.TextChoices):
        NOT_MARKED = "NOT_MARKED", _("Not marked")
        PRESENT = "PRESENT", _("Present")
        ABSENT = "ABSENT", _("Absent")
        EXCUSED = "EXCUSED", _("Excused")

    class PreferredLanguage(models.TextChoices):
        SWAHILI = "sw", _("Kiswahili")
        ENGLISH = "en", _("English")

    meeting = models.ForeignKey(
        Meeting,
        verbose_name=_("meeting"),
        related_name="attendees",
        on_delete=models.CASCADE,
    )
    response_token = models.UUIDField(
        _("invitation response token"),
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )
    attendee_type = models.CharField(
        _("participant type"),
        max_length=20,
        choices=AttendeeType.choices,
        default=AttendeeType.EXTERNAL,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("system user"),
        related_name="meeting_attendance_records",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    full_name = models.CharField(_("full name"), max_length=200)
    organization = models.CharField(
        _("organization"),
        max_length=250,
        blank=True,
    )
    designation = models.CharField(
        _("designation"),
        max_length=150,
        blank=True,
    )
    email = models.EmailField(_("email address"), blank=True)
    phone_number = models.CharField(
        _("phone number"),
        max_length=30,
        blank=True,
    )
    preferred_language = models.CharField(
        _("preferred language"),
        max_length=5,
        choices=PreferredLanguage.choices,
        default=PreferredLanguage.SWAHILI,
    )
    response_status = models.CharField(
        _("invitation response"),
        max_length=20,
        choices=ResponseStatus.choices,
        default=ResponseStatus.INVITED,
    )
    attendance_status = models.CharField(
        _("attendance status"),
        max_length=20,
        choices=AttendanceStatus.choices,
        default=AttendanceStatus.NOT_MARKED,
    )
    invitation_sent_at = models.DateTimeField(
        _("invitation sent at"),
        null=True,
        blank=True,
    )
    responded_at = models.DateTimeField(
        _("invitation responded at"),
        null=True,
        blank=True,
    )
    checked_in_at = models.DateTimeField(
        _("checked in at"),
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = _("meeting participant")
        verbose_name_plural = _("meeting participants")
        ordering = ["meeting", "full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["meeting", "user"],
                condition=Q(user__isnull=False),
                name="unique_internal_attendee_per_meeting",
            ),
            models.UniqueConstraint(
                fields=["meeting", "email"],
                condition=~Q(email=""),
                name="unique_attendee_email_per_meeting",
            ),
        ]
        indexes = [
            models.Index(
                fields=["meeting", "attendance_status"],
                name="meeting_attendance_idx",
            ),
        ]

    def clean(self):
        if self.attendee_type == self.AttendeeType.INTERNAL and not self.user_id:
            raise ValidationError({
                "user": _("Select a system user for an internal participant."),
            })

    def save(self, *args, **kwargs):
        if self.user_id:
            if not self.full_name.strip():
                self.full_name = self.user.get_full_name().strip() or self.user.username
            if not self.email:
                self.email = self.user.email
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} - {self.meeting.reference_number}"


class MeetingDecision(BaseModel):
    class Status(models.TextChoices):
        PROPOSED = "PROPOSED", _("Proposed")
        APPROVED = "APPROVED", _("Approved")
        DEFERRED = "DEFERRED", _("Deferred")

    meeting = models.ForeignKey(
        Meeting,
        verbose_name=_("meeting"),
        related_name="decisions",
        on_delete=models.CASCADE,
    )
    agenda_item = models.ForeignKey(
        MeetingAgendaItem,
        verbose_name=_("agenda item"),
        related_name="decisions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    decision_number = models.PositiveIntegerField(_("decision number"))
    decision_sw = models.TextField(_("decision in Kiswahili"))
    decision_en = models.TextField(_("decision in English"), blank=True)
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=Status.choices,
        default=Status.APPROVED,
    )

    class Meta:
        verbose_name = _("meeting decision")
        verbose_name_plural = _("meeting decisions")
        ordering = ["meeting", "decision_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["meeting", "decision_number"],
                name="unique_decision_number_per_meeting",
            ),
        ]

    def clean(self):
        if self.agenda_item_id and self.agenda_item.meeting_id != self.meeting_id:
            raise ValidationError({
                "agenda_item": _("The agenda item must belong to this meeting."),
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.meeting.reference_number} - {self.decision_number}"


class MeetingActionItem(BaseModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", _("Pending")
        IN_PROGRESS = "IN_PROGRESS", _("In progress")
        COMPLETED = "COMPLETED", _("Completed")
        OVERDUE = "OVERDUE", _("Overdue")
        CANCELLED = "CANCELLED", _("Cancelled")

    meeting = models.ForeignKey(
        Meeting,
        verbose_name=_("meeting"),
        related_name="action_items",
        on_delete=models.CASCADE,
    )
    decision = models.ForeignKey(
        MeetingDecision,
        verbose_name=_("decision"),
        related_name="action_items",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    action_number = models.PositiveIntegerField(_("action number"))
    description_sw = models.TextField(_("action in Kiswahili"))
    description_en = models.TextField(_("action in English"), blank=True)
    responsible_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("responsible system user"),
        related_name="meeting_action_items",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    responsible_name = models.CharField(
        _("responsible person"),
        max_length=200,
        blank=True,
    )
    responsible_email = models.EmailField(
        _("responsible person's email"),
        blank=True,
    )
    due_date = models.DateField(_("due date"), null=True, blank=True)
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    progress_notes = models.TextField(_("progress notes"), blank=True)
    completed_at = models.DateTimeField(
        _("completed at"),
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = _("meeting action item")
        verbose_name_plural = _("meeting action items")
        ordering = ["meeting", "action_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["meeting", "action_number"],
                name="unique_action_number_per_meeting",
            ),
        ]
        indexes = [
            models.Index(
                fields=["status", "due_date"],
                name="meeting_action_due_idx",
            ),
        ]

    def clean(self):
        errors = {}
        if self.decision_id and self.decision.meeting_id != self.meeting_id:
            errors["decision"] = _("The decision must belong to this meeting.")
        if not self.responsible_user_id and not self.responsible_name.strip():
            errors["responsible_name"] = _(
                "Enter a responsible person or select a system user."
            )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.responsible_user_id and not self.responsible_name.strip():
            self.responsible_name = (
                self.responsible_user.get_full_name().strip()
                or self.responsible_user.username
            )
        if self.responsible_user_id and not self.responsible_email:
            self.responsible_email = self.responsible_user.email
        if self.status == self.Status.COMPLETED and not self.completed_at:
            self.completed_at = timezone.now()
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.meeting.reference_number} - {self.action_number}"


class MeetingCommunicationLog(BaseModel):
    class CommunicationType(models.TextChoices):
        INVITATION = "INVITATION", _("Meeting invitation")
        RSVP_REMINDER = "RSVP_REMINDER", _("Attendance confirmation reminder")
        ACTION_REMINDER = "ACTION_REMINDER", _("Action deadline reminder")

    class DeliveryStatus(models.TextChoices):
        SENT = "SENT", _("Sent")
        FAILED = "FAILED", _("Failed")

    meeting = models.ForeignKey(
        Meeting,
        verbose_name=_("meeting"),
        related_name="communications",
        on_delete=models.CASCADE,
    )
    attendee = models.ForeignKey(
        MeetingAttendee,
        verbose_name=_("meeting participant"),
        related_name="communications",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    action_item = models.ForeignKey(
        MeetingActionItem,
        verbose_name=_("meeting action item"),
        related_name="communications",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    communication_type = models.CharField(
        _("communication type"),
        max_length=30,
        choices=CommunicationType.choices,
    )
    delivery_status = models.CharField(
        _("delivery status"),
        max_length=20,
        choices=DeliveryStatus.choices,
    )
    recipient_name = models.CharField(_("recipient name"), max_length=200)
    recipient_email = models.EmailField(_("recipient email"))
    subject = models.CharField(_("subject"), max_length=300)
    message = models.TextField(_("message"))
    sent_at = models.DateTimeField(_("sent at"), default=timezone.now)
    error_message = models.TextField(_("error message"), blank=True)

    class Meta:
        verbose_name = _("meeting communication")
        verbose_name_plural = _("meeting communications")
        ordering = ["-sent_at", "-created_at"]
        indexes = [
            models.Index(
                fields=["meeting", "communication_type", "delivery_status"],
                name="meeting_comm_status_idx",
            ),
        ]

    def __str__(self):
        return f"{self.meeting.reference_number} - {self.recipient_email}"
