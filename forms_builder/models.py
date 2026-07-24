from django.db import models
from django.utils.text import slugify
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel
from events.models import Event


class EventForm(BaseModel):
    class FormType(models.TextChoices):
        REGISTRATION = "REGISTRATION", _("Registration Form")
        EVALUATION = "EVALUATION", _("Evaluation Form")
        EXHIBITOR = "EXHIBITOR", _("Exhibitor Form")
        SPEAKER = "SPEAKER", _("Speaker Application Form")
        ATTENDANCE = "ATTENDANCE", _("Attendance Confirmation Form")
        OTHER = "OTHER", _("Other Form")

    event = models.ForeignKey(
        Event,
        verbose_name=_("event"),
        related_name="forms",
        on_delete=models.CASCADE,
    )

    name_sw = models.CharField(
        _("form name in Kiswahili"),
        max_length=200,
    )

    name_en = models.CharField(
        _("form name in English"),
        max_length=200,
    )

    form_type = models.CharField(
        _("form type"),
        max_length=30,
        choices=FormType.choices,
        default=FormType.REGISTRATION,
    )

    slug = models.SlugField(
        _("slug"),
        max_length=250,
        blank=True,
    )

    introduction_sw = models.TextField(
        _("introduction in Kiswahili"),
        blank=True,
    )

    introduction_en = models.TextField(
        _("introduction in English"),
        blank=True,
    )

    success_message_sw = models.TextField(
        _("success message in Kiswahili"),
        blank=True,
        default="Taarifa zako zimepokelewa kwa mafanikio.",
    )

    success_message_en = models.TextField(
        _("success message in English"),
        blank=True,
        default="Your information has been submitted successfully.",
    )

    opens_at = models.DateTimeField(
        _("form opens"),
        null=True,
        blank=True,
    )

    closes_at = models.DateTimeField(
        _("form closes"),
        null=True,
        blank=True,
    )

    requires_login = models.BooleanField(
        _("requires login"),
        default=False,
    )

    allow_multiple_submissions = models.BooleanField(
        _("allow multiple submissions"),
        default=False,
    )

    is_published = models.BooleanField(
        _("published"),
        default=False,
    )

    class Meta:
        verbose_name = _("event form")
        verbose_name_plural = _("event forms")
        ordering = ["event", "form_type", "name_sw"]

        constraints = [
            models.UniqueConstraint(
                fields=["event", "slug"],
                name="unique_form_slug_per_event",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name_en or self.name_sw)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.event.code} - {self.name_sw}"


class FormSection(BaseModel):
    event_form = models.ForeignKey(
        EventForm,
        verbose_name=_("event form"),
        related_name="sections",
        on_delete=models.CASCADE,
    )

    title_sw = models.CharField(
        _("section title in Kiswahili"),
        max_length=200,
    )

    title_en = models.CharField(
        _("section title in English"),
        max_length=200,
    )

    description_sw = models.TextField(
        _("section description in Kiswahili"),
        blank=True,
    )

    description_en = models.TextField(
        _("section description in English"),
        blank=True,
    )

    display_order = models.PositiveIntegerField(
        _("display order"),
        default=0,
    )

    class Meta:
        verbose_name = _("form section")
        verbose_name_plural = _("form sections")
        ordering = ["event_form", "display_order", "id"]

    def __str__(self):
        return f"{self.event_form.name_sw} - {self.title_sw}"


class FormQuestion(BaseModel):
    class QuestionType(models.TextChoices):
        SHORT_TEXT = "SHORT_TEXT", _("Short text")
        LONG_TEXT = "LONG_TEXT", _("Long text")
        EMAIL = "EMAIL", _("Email address")
        PHONE = "PHONE", _("Phone number")
        NUMBER = "NUMBER", _("Number")
        DATE = "DATE", _("Date")
        DATETIME = "DATETIME", _("Date and time")
        SINGLE_CHOICE = "SINGLE_CHOICE", _("Single choice")
        MULTIPLE_CHOICE = "MULTIPLE_CHOICE", _("Multiple choice")
        DROPDOWN = "DROPDOWN", _("Dropdown")
        YES_NO = "YES_NO", _("Yes or No")
        FILE = "FILE", _("File upload")
        IMAGE = "IMAGE", _("Image upload")

    section = models.ForeignKey(
        FormSection,
        verbose_name=_("form section"),
        related_name="questions",
        on_delete=models.CASCADE,
    )

    label_sw = models.CharField(
        _("question in Kiswahili"),
        max_length=300,
    )

    label_en = models.CharField(
        _("question in English"),
        max_length=300,
    )

    question_type = models.CharField(
        _("question type"),
        max_length=30,
        choices=QuestionType.choices,
        default=QuestionType.SHORT_TEXT,
    )

    help_text_sw = models.CharField(
        _("help text in Kiswahili"),
        max_length=300,
        blank=True,
    )

    help_text_en = models.CharField(
        _("help text in English"),
        max_length=300,
        blank=True,
    )

    placeholder_sw = models.CharField(
        _("placeholder in Kiswahili"),
        max_length=200,
        blank=True,
    )

    placeholder_en = models.CharField(
        _("placeholder in English"),
        max_length=200,
        blank=True,
    )

    is_required = models.BooleanField(
        _("required"),
        default=False,
    )

    display_order = models.PositiveIntegerField(
        _("display order"),
        default=0,
    )

    minimum_length = models.PositiveIntegerField(
        _("minimum length"),
        null=True,
        blank=True,
    )

    maximum_length = models.PositiveIntegerField(
        _("maximum length"),
        null=True,
        blank=True,
    )

    minimum_value = models.DecimalField(
        _("minimum value"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    maximum_value = models.DecimalField(
        _("maximum value"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = _("form question")
        verbose_name_plural = _("form questions")
        ordering = ["section", "display_order", "id"]

    def __str__(self):
        return self.label_sw


class QuestionOption(BaseModel):
    question = models.ForeignKey(
        FormQuestion,
        verbose_name=_("question"),
        related_name="options",
        on_delete=models.CASCADE,
    )

    value = models.CharField(
        _("stored value"),
        max_length=100,
    )

    label_sw = models.CharField(
        _("option in Kiswahili"),
        max_length=200,
    )

    label_en = models.CharField(
        _("option in English"),
        max_length=200,
    )

    display_order = models.PositiveIntegerField(
        _("display order"),
        default=0,
    )

    class Meta:
        verbose_name = _("question option")
        verbose_name_plural = _("question options")
        ordering = ["question", "display_order", "id"]

        constraints = [
            models.UniqueConstraint(
                fields=["question", "value"],
                name="unique_option_value_per_question",
            ),
        ]

    def __str__(self):
        return self.label_sw

class FormSubmission(BaseModel):
    event_form = models.ForeignKey(
        EventForm,
        verbose_name=_("event form"),
        related_name="submissions",
        on_delete=models.CASCADE,
    )

    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("submitted by"),
        related_name="event_form_submissions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    reference_number = models.CharField(
        _("reference number"),
        max_length=60,
        unique=True,
        blank=True,
    )

    language = models.CharField(
        _("submission language"),
        max_length=5,
        choices=(
            ("sw", _("Kiswahili")),
            ("en", _("English")),
        ),
        default="sw",
    )

    submitter_email = models.EmailField(
        _("submitter email"),
        blank=True,
    )

    submitter_phone = models.CharField(
        _("submitter phone"),
        max_length=30,
        blank=True,
    )

    ip_address = models.GenericIPAddressField(
        _("IP address"),
        null=True,
        blank=True,
    )

    user_agent = models.TextField(
        _("user agent"),
        blank=True,
    )

    is_complete = models.BooleanField(
        _("complete submission"),
        default=True,
    )

    class Meta:
        verbose_name = _("form submission")
        verbose_name_plural = _("form submissions")
        ordering = ["-created_at"]

        indexes = [
            models.Index(
                fields=["event_form", "created_at"],
                name="form_submit_created_idx",
            ),
            models.Index(
                fields=["reference_number"],
                name="form_submit_ref_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.reference_number:
            prefix = self.event_form.event.code.replace(" ", "-").upper()
            form_code = self.event_form.form_type[:3].upper()

            latest_id = (
                FormSubmission.objects
                .filter(event_form=self.event_form)
                .order_by("-id")
                .values_list("id", flat=True)
                .first()
                or 0
            )

            self.reference_number = (
                f"{prefix}-{form_code}-{latest_id + 1:05d}"
            )

        super().save(*args, **kwargs)

    def __str__(self):
        return self.reference_number


class FormAnswer(BaseModel):
    submission = models.ForeignKey(
        FormSubmission,
        verbose_name=_("submission"),
        related_name="answers",
        on_delete=models.CASCADE,
    )

    question = models.ForeignKey(
        FormQuestion,
        verbose_name=_("question"),
        related_name="answers",
        on_delete=models.PROTECT,
    )

    text_value = models.TextField(
        _("text value"),
        blank=True,
    )

    number_value = models.DecimalField(
        _("number value"),
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
    )

    date_value = models.DateField(
        _("date value"),
        null=True,
        blank=True,
    )

    datetime_value = models.DateTimeField(
        _("date and time value"),
        null=True,
        blank=True,
    )

    boolean_value = models.BooleanField(
        _("boolean value"),
        null=True,
        blank=True,
    )

    selected_options = models.ManyToManyField(
        QuestionOption,
        verbose_name=_("selected options"),
        related_name="answers",
        blank=True,
    )

    uploaded_file = models.FileField(
        _("uploaded file"),
        upload_to="form_submissions/files/",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = _("form answer")
        verbose_name_plural = _("form answers")
        ordering = ["submission", "question__display_order"]

        constraints = [
            models.UniqueConstraint(
                fields=["submission", "question"],
                name="unique_answer_per_submission_question",
            ),
        ]

    def __str__(self):
        return f"{self.submission.reference_number} - {self.question}"