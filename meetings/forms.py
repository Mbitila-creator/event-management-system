from datetime import timedelta
from pathlib import Path

from django import forms
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from accounts.models import User
from events.models import Event, EventCategory, Venue

from .models import (
    ALLOWED_MEETING_DOCUMENT_EXTENSIONS,
    MAX_MEETING_DOCUMENT_SIZE,
    Meeting,
    MeetingActionItem,
    MeetingAgendaItem,
    MeetingAttendee,
    MeetingDecision,
    MeetingDocument,
    MeetingSeries,
    MeetingSeriesAgendaTemplate,
)


DATETIME_FORMAT = "%Y-%m-%dT%H:%M"


def validate_meeting_upload(uploaded_file):
    extension = Path(uploaded_file.name).suffix.lower()
    if extension not in ALLOWED_MEETING_DOCUMENT_EXTENSIONS:
        raise forms.ValidationError(
            _("Upload a PDF, Office document, text file, or image."),
        )
    if uploaded_file.size > MAX_MEETING_DOCUMENT_SIZE:
        raise forms.ValidationError(
            _("The document must not exceed 20 MB."),
        )
    return uploaded_file


class MeetingWorkflowForm(forms.Form):
    """Create or update the shared event and its meeting profile together."""

    code = forms.CharField(label=_("Event code"), max_length=50)
    reference_number = forms.CharField(
        label=_("Meeting reference number"),
        max_length=80,
    )
    title_sw = forms.CharField(label=_("Meeting title in Kiswahili"), max_length=250)
    title_en = forms.CharField(label=_("Meeting title in English"), max_length=250)
    description_sw = forms.CharField(
        label=_("Description in Kiswahili"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    description_en = forms.CharField(
        label=_("Description in English"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    organizer_name_sw = forms.CharField(
        label=_("Organizer in Kiswahili"),
        max_length=250,
        required=False,
    )
    organizer_name_en = forms.CharField(
        label=_("Organizer in English"),
        max_length=250,
        required=False,
    )
    venue = forms.ModelChoiceField(
        label=_("Venue"),
        queryset=Venue.objects.none(),
        required=False,
    )
    starts_at = forms.DateTimeField(
        label=_("Meeting starts"),
        input_formats=[DATETIME_FORMAT],
        widget=forms.DateTimeInput(
            format=DATETIME_FORMAT,
            attrs={"type": "datetime-local"},
        ),
    )
    ends_at = forms.DateTimeField(
        label=_("Meeting ends"),
        input_formats=[DATETIME_FORMAT],
        widget=forms.DateTimeInput(
            format=DATETIME_FORMAT,
            attrs={"type": "datetime-local"},
        ),
    )
    status = forms.ChoiceField(label=_("Status"), choices=Event.Status.choices)
    is_public = forms.BooleanField(label=_("Public meeting"), required=False)
    meeting_type = forms.ChoiceField(
        label=_("Meeting type"),
        choices=Meeting.MeetingType.choices,
    )
    chairperson_name = forms.CharField(label=_("Chairperson"), max_length=200)
    secretary_name = forms.CharField(
        label=_("Meeting secretary"),
        max_length=200,
        required=False,
    )
    quorum_required = forms.IntegerField(
        label=_("Required quorum"),
        min_value=1,
        required=False,
    )
    invitation_deadline = forms.DateTimeField(
        label=_("Invitation response deadline"),
        required=False,
        input_formats=[DATETIME_FORMAT],
        widget=forms.DateTimeInput(
            format=DATETIME_FORMAT,
            attrs={"type": "datetime-local"},
        ),
    )
    objectives_sw = forms.CharField(
        label=_("Objectives in Kiswahili"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    objectives_en = forms.CharField(
        label=_("Objectives in English"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance
        super().__init__(*args, **kwargs)
        self.fields["venue"].queryset = Venue.objects.filter(
            is_active=True,
        ).select_related("council").order_by("name")
        if instance and not self.is_bound:
            event = instance.event
            self.initial.update({
                "code": event.code,
                "reference_number": instance.reference_number,
                "title_sw": event.title_sw,
                "title_en": event.title_en,
                "description_sw": event.description_sw,
                "description_en": event.description_en,
                "organizer_name_sw": event.organizer_name_sw,
                "organizer_name_en": event.organizer_name_en,
                "venue": event.venue_id,
                "starts_at": timezone.localtime(event.starts_at).strftime(
                    DATETIME_FORMAT
                ),
                "ends_at": timezone.localtime(event.ends_at).strftime(
                    DATETIME_FORMAT
                ),
                "status": event.status,
                "is_public": event.is_public,
                "meeting_type": instance.meeting_type,
                "chairperson_name": instance.chairperson_name,
                "secretary_name": instance.secretary_name,
                "quorum_required": instance.quorum_required,
                "invitation_deadline": (
                    timezone.localtime(instance.invitation_deadline).strftime(
                        DATETIME_FORMAT
                    )
                    if instance.invitation_deadline
                    else ""
                ),
                "objectives_sw": instance.objectives_sw,
                "objectives_en": instance.objectives_en,
            })

    def clean_code(self):
        code = self.cleaned_data["code"].strip().upper()
        existing = Event.objects.filter(code=code)
        if self.instance:
            existing = existing.exclude(pk=self.instance.event_id)
        if existing.exists():
            raise forms.ValidationError(_("An event with this code already exists."))
        return code

    def clean_reference_number(self):
        reference = self.cleaned_data["reference_number"].strip().upper()
        existing = Meeting.objects.filter(reference_number=reference)
        if self.instance:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise forms.ValidationError(
                _("A meeting with this reference number already exists.")
            )
        return reference

    def clean(self):
        cleaned = super().clean()
        starts_at = cleaned.get("starts_at")
        ends_at = cleaned.get("ends_at")
        deadline = cleaned.get("invitation_deadline")
        if starts_at and ends_at and ends_at <= starts_at:
            self.add_error("ends_at", _("The meeting must end after it starts."))
        if starts_at and deadline and deadline > starts_at:
            self.add_error(
                "invitation_deadline",
                _("The invitation deadline cannot be after the meeting starts."),
            )
        return cleaned

    @transaction.atomic
    def save(self, user):
        category, created = EventCategory.objects.get_or_create(
            code="MEETING",
            defaults={
                "name_sw": "Vikao",
                "name_en": "Meetings",
                "description_sw": "Vikao na mikutano rasmi",
                "description_en": "Formal meetings and working sessions",
                "created_by": user,
                "updated_by": user,
            },
        )
        if not created and not category.is_active:
            category.is_active = True
            category.updated_by = user
            category.save(update_fields=["is_active", "updated_by", "updated_at"])

        event = self.instance.event if self.instance else Event(category=category)
        event.category = category
        for field in (
            "code", "title_sw", "title_en", "description_sw", "description_en",
            "organizer_name_sw", "organizer_name_en", "venue", "starts_at",
            "ends_at", "status", "is_public",
        ):
            setattr(event, field, self.cleaned_data[field])
        event.registration_enabled = False
        event.qr_checkin_enabled = False
        if not event.pk:
            event.created_by = user
        event.updated_by = user
        event.save()

        meeting = self.instance or Meeting(event=event)
        for field in (
            "reference_number", "meeting_type", "chairperson_name",
            "secretary_name", "quorum_required", "invitation_deadline",
            "objectives_sw", "objectives_en",
        ):
            setattr(meeting, field, self.cleaned_data[field])
        if not meeting.pk:
            meeting.created_by = user
        meeting.updated_by = user
        meeting.save()
        return meeting


class MeetingAgendaItemForm(forms.ModelForm):
    class Meta:
        model = MeetingAgendaItem
        fields = (
            "item_number", "title_sw", "title_en", "presenter_name",
            "allocated_minutes", "notes",
        )
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}


class MeetingDocumentForm(forms.ModelForm):
    class Meta:
        model = MeetingDocument
        fields = (
            "document_type", "agenda_item", "title_sw", "title_en",
            "description_sw", "description_en", "file", "version",
            "is_confidential",
        )
        widgets = {
            "description_sw": forms.Textarea(attrs={"rows": 2}),
            "description_en": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, meeting, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["agenda_item"].queryset = meeting.agenda_items.filter(
            is_active=True,
        ).order_by("item_number")
        self.fields["file"].widget.attrs["accept"] = ",".join(
            sorted(ALLOWED_MEETING_DOCUMENT_EXTENSIONS)
        )

    def clean_file(self):
        return validate_meeting_upload(self.cleaned_data["file"])


class MeetingAttendeeForm(forms.ModelForm):
    class Meta:
        model = MeetingAttendee
        fields = (
            "attendee_type", "user", "full_name", "organization", "designation",
            "email", "phone_number", "preferred_language",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["full_name"].required = False
        self.fields["user"].queryset = User.objects.filter(
            is_active=True,
        ).order_by("first_name", "last_name", "username")

    def clean_full_name(self):
        full_name = self.cleaned_data.get("full_name", "").strip()
        user = self.cleaned_data.get("user")
        if not full_name and user:
            return user.get_full_name().strip() or user.username
        if not full_name:
            raise forms.ValidationError(_("Enter the participant's full name."))
        return full_name


class MeetingMinutesForm(forms.ModelForm):
    class Meta:
        model = Meeting
        fields = ("minutes_sw", "minutes_en", "minutes_document")
        widgets = {
            "minutes_sw": forms.Textarea(attrs={"rows": 6}),
            "minutes_en": forms.Textarea(attrs={"rows": 6}),
        }

    def clean_minutes_document(self):
        uploaded_file = self.cleaned_data.get("minutes_document")
        if uploaded_file:
            return validate_meeting_upload(uploaded_file)
        return uploaded_file


class MinutesApprovalForm(forms.Form):
    comment = forms.CharField(
        label=_("Approval comment"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )


class MinutesReturnForm(forms.Form):
    comment = forms.CharField(
        label=_("Reason for correction"),
        widget=forms.Textarea(attrs={"rows": 2}),
    )


class MeetingDecisionForm(forms.ModelForm):
    class Meta:
        model = MeetingDecision
        fields = (
            "agenda_item", "decision_number", "decision_sw", "decision_en", "status",
        )
        widgets = {
            "decision_sw": forms.Textarea(attrs={"rows": 3}),
            "decision_en": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, meeting, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["agenda_item"].queryset = meeting.agenda_items.filter(
            is_active=True,
        ).order_by("item_number")


class MeetingActionItemForm(forms.ModelForm):
    class Meta:
        model = MeetingActionItem
        fields = (
            "decision", "action_number", "description_sw", "description_en",
            "responsible_user", "responsible_name", "responsible_email",
            "due_date", "status", "progress_notes",
        )
        widgets = {
            "description_sw": forms.Textarea(attrs={"rows": 3}),
            "description_en": forms.Textarea(attrs={"rows": 3}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "progress_notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, meeting, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["decision"].queryset = meeting.decisions.filter(
            is_active=True,
        ).order_by("decision_number")
        self.fields["responsible_user"].queryset = User.objects.filter(
            is_active=True,
        ).order_by("first_name", "last_name", "username")


class AttendeeProgressForm(forms.Form):
    response_status = forms.ChoiceField(
        label=_("Invitation response"),
        choices=MeetingAttendee.ResponseStatus.choices,
    )
    attendance_status = forms.ChoiceField(
        label=_("Attendance status"),
        choices=MeetingAttendee.AttendanceStatus.choices,
    )


class AttendanceOnlyForm(forms.Form):
    attendance_status = forms.ChoiceField(
        label=_("Attendance status"),
        choices=MeetingAttendee.AttendanceStatus.choices,
    )


class ActionProgressForm(forms.Form):
    status = forms.ChoiceField(
        label=_("Status"),
        choices=MeetingActionItem.Status.choices,
    )
    progress_notes = forms.CharField(
        label=_("Progress notes"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )


class InvitationResponseForm(forms.Form):
    response_status = forms.ChoiceField(
        label=_("Your response"),
        choices=(
            (MeetingAttendee.ResponseStatus.ACCEPTED, _("I will attend")),
            (MeetingAttendee.ResponseStatus.TENTATIVE, _("I may attend")),
            (MeetingAttendee.ResponseStatus.DECLINED, _("I will not attend")),
        ),
        widget=forms.RadioSelect,
    )


class MeetingSeriesForm(forms.ModelForm):
    class Meta:
        model = MeetingSeries
        fields = (
            "code", "name_sw", "name_en", "description_sw", "description_en",
            "frequency", "meeting_type", "default_duration_minutes", "venue",
            "chairperson_name", "secretary_name", "quorum_required",
            "objectives_sw", "objectives_en", "is_active",
        )
        widgets = {
            "description_sw": forms.Textarea(attrs={"rows": 3}),
            "description_en": forms.Textarea(attrs={"rows": 3}),
            "objectives_sw": forms.Textarea(attrs={"rows": 3}),
            "objectives_en": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["venue"].queryset = Venue.objects.filter(
            is_active=True,
        ).select_related("council").order_by("name")


class MeetingSeriesAgendaTemplateForm(forms.ModelForm):
    class Meta:
        model = MeetingSeriesAgendaTemplate
        fields = (
            "item_number", "title_sw", "title_en", "presenter_name",
            "allocated_minutes", "notes",
        )
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}


class MeetingOccurrenceForm(forms.Form):
    code = forms.CharField(label=_("Event code"), max_length=50)
    reference_number = forms.CharField(
        label=_("Meeting reference number"),
        max_length=80,
    )
    title_sw = forms.CharField(label=_("Meeting title in Kiswahili"), max_length=250)
    title_en = forms.CharField(label=_("Meeting title in English"), max_length=250)
    starts_at = forms.DateTimeField(
        label=_("Meeting starts"),
        input_formats=[DATETIME_FORMAT],
        widget=forms.DateTimeInput(
            format=DATETIME_FORMAT,
            attrs={"type": "datetime-local"},
        ),
    )
    invitation_deadline = forms.DateTimeField(
        label=_("Invitation response deadline"),
        required=False,
        input_formats=[DATETIME_FORMAT],
        widget=forms.DateTimeInput(
            format=DATETIME_FORMAT,
            attrs={"type": "datetime-local"},
        ),
    )
    status = forms.ChoiceField(label=_("Status"), choices=Event.Status.choices)
    is_public = forms.BooleanField(label=_("Public meeting"), required=False)
    copy_participants = forms.BooleanField(
        label=_("Copy participants from the latest meeting in this series"),
        required=False,
        initial=True,
    )

    def __init__(self, *args, series, **kwargs):
        self.series = series
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial.update({
                "title_sw": series.name_sw,
                "title_en": series.name_en,
                "status": Event.Status.DRAFT,
            })

    def clean_code(self):
        code = self.cleaned_data["code"].strip().upper()
        if Event.objects.filter(code=code).exists():
            raise forms.ValidationError(_("An event with this code already exists."))
        return code

    def clean_reference_number(self):
        reference = self.cleaned_data["reference_number"].strip().upper()
        if Meeting.objects.filter(reference_number=reference).exists():
            raise forms.ValidationError(
                _("A meeting with this reference number already exists.")
            )
        return reference

    def clean(self):
        cleaned = super().clean()
        starts_at = cleaned.get("starts_at")
        deadline = cleaned.get("invitation_deadline")
        if starts_at and deadline and deadline > starts_at:
            self.add_error(
                "invitation_deadline",
                _("The invitation deadline cannot be after the meeting starts."),
            )
        return cleaned

    @transaction.atomic
    def save(self, user):
        category, created = EventCategory.objects.get_or_create(
            code="MEETING",
            defaults={
                "name_sw": "Vikao",
                "name_en": "Meetings",
                "created_by": user,
                "updated_by": user,
            },
        )
        if not created and not category.is_active:
            category.is_active = True
            category.updated_by = user
            category.save(update_fields=["is_active", "updated_by", "updated_at"])
        starts_at = self.cleaned_data["starts_at"]
        event = Event.objects.create(
            category=category,
            venue=self.series.venue,
            code=self.cleaned_data["code"],
            title_sw=self.cleaned_data["title_sw"],
            title_en=self.cleaned_data["title_en"],
            description_sw=self.series.description_sw,
            description_en=self.series.description_en,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(
                minutes=self.series.default_duration_minutes,
            ),
            status=self.cleaned_data["status"],
            is_public=self.cleaned_data["is_public"],
            registration_enabled=False,
            qr_checkin_enabled=False,
            created_by=user,
            updated_by=user,
        )
        meeting = Meeting.objects.create(
            event=event,
            series=self.series,
            reference_number=self.cleaned_data["reference_number"],
            meeting_type=self.series.meeting_type,
            chairperson_name=self.series.chairperson_name,
            secretary_name=self.series.secretary_name,
            quorum_required=self.series.quorum_required,
            invitation_deadline=self.cleaned_data["invitation_deadline"],
            objectives_sw=self.series.objectives_sw,
            objectives_en=self.series.objectives_en,
            created_by=user,
            updated_by=user,
        )
        for template in self.series.agenda_templates.filter(is_active=True):
            MeetingAgendaItem.objects.create(
                meeting=meeting,
                item_number=template.item_number,
                title_sw=template.title_sw,
                title_en=template.title_en,
                presenter_name=template.presenter_name,
                allocated_minutes=template.allocated_minutes,
                notes=template.notes,
                created_by=user,
                updated_by=user,
            )
        if self.cleaned_data["copy_participants"]:
            source = self.series.meetings.exclude(pk=meeting.pk).order_by(
                "-event__starts_at",
            ).first()
            if source:
                for attendee in source.attendees.filter(is_active=True):
                    MeetingAttendee.objects.create(
                        meeting=meeting,
                        attendee_type=attendee.attendee_type,
                        user=attendee.user,
                        full_name=attendee.full_name,
                        organization=attendee.organization,
                        designation=attendee.designation,
                        email=attendee.email,
                        phone_number=attendee.phone_number,
                        preferred_language=attendee.preferred_language,
                        created_by=user,
                        updated_by=user,
                    )
        return meeting
