from django.contrib import admin, messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    EventForm,
    FormAnswer,
    FormQuestion,
    FormSection,
    FormSubmission,
    QuestionOption,
)
from .services import (
    generate_qr_png,
    public_form_path,
    public_form_url,
    submissions_csv,
)


class AuditAdminMixin:
    readonly_fields = (
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    )

    def save_model(self, request, obj, form, change):
        if not obj.pk or not obj.created_by:
            obj.created_by = request.user

        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


class FormSectionInline(admin.TabularInline):
    model = FormSection
    extra = 0
    fields = (
        "title_sw",
        "title_en",
        "display_order",
        "is_active",
    )


class QuestionOptionInline(admin.TabularInline):
    model = QuestionOption
    extra = 0
    fields = (
        "value",
        "label_sw",
        "label_en",
        "display_order",
        "is_active",
    )


@admin.register(EventForm)
class EventFormAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = (
        "name_sw",
        "event",
        "form_type",
        "is_published",
        "registration_tools",
        "requires_login",
        "is_active",
    )

    list_filter = (
        "form_type",
        "is_published",
        "requires_login",
        "allow_multiple_submissions",
        "is_active",
    )

    search_fields = (
        "name_sw",
        "name_en",
        "event__code",
        "event__title_sw",
        "event__title_en",
    )

    readonly_fields = AuditAdminMixin.readonly_fields + (
        "slug",
        "registration_tools",
    )

    inlines = [
        FormSectionInline,
    ]

    @admin.display(description="Registration link and QR code")
    def registration_tools(self, obj):
        if not obj or not obj.pk:
            return "Save the form first."

        if not obj.is_published or not obj.is_active:
            return "Publish and activate the form first."

        public_url = public_form_path(obj)
        qr_url = reverse(
            "admin:forms_builder_eventform_qr_code",
            args=[obj.pk],
        )
        download_url = f"{qr_url}?download=1"

        return format_html(
            '<a href="{}" target="_blank" rel="noopener">Open form</a>'
            ' &nbsp;|&nbsp; '
            '<a href="{}" target="_blank" rel="noopener">View QR</a>'
            ' &nbsp;|&nbsp; '
            '<a href="{}">Download QR</a>',
            public_url,
            qr_url,
            download_url,
        )

    def get_urls(self):
        custom_urls = [
            path(
                "<int:form_id>/qr-code/",
                self.admin_site.admin_view(self.qr_code_view),
                name="forms_builder_eventform_qr_code",
            ),
        ]
        return custom_urls + super().get_urls()

    def qr_code_view(self, request, form_id):
        event_form = get_object_or_404(
            EventForm.objects.select_related("event"),
            pk=form_id,
            is_active=True,
            is_published=True,
        )
        registration_url = public_form_url(
            event_form,
            request=request,
            language="sw",
        )
        image_data = generate_qr_png(registration_url)
        response = HttpResponse(image_data, content_type="image/png")

        if request.GET.get("download") == "1":
            filename = (
                f"{event_form.event.code}-"
                f"{event_form.slug}-registration-qr.png"
            )
            response["Content-Disposition"] = (
                f'attachment; filename="{filename}"'
            )

        response["X-Content-Type-Options"] = "nosniff"
        return response


@admin.register(FormSection)
class FormSectionAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = (
        "title_sw",
        "event_form",
        "display_order",
        "is_active",
    )

    list_filter = (
        "event_form__event",
        "event_form",
        "is_active",
    )

    search_fields = (
        "title_sw",
        "title_en",
        "event_form__name_sw",
        "event_form__name_en",
    )

    ordering = (
        "event_form",
        "display_order",
    )


@admin.register(FormQuestion)
class FormQuestionAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = (
        "label_sw",
        "section",
        "question_type",
        "is_required",
        "display_order",
        "is_active",
    )

    list_filter = (
        "question_type",
        "is_required",
        "section__event_form",
        "is_active",
    )

    search_fields = (
        "label_sw",
        "label_en",
        "section__title_sw",
        "section__title_en",
    )

    ordering = (
        "section",
        "display_order",
    )

    inlines = [
        QuestionOptionInline,
    ]


@admin.register(QuestionOption)
class QuestionOptionAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = (
        "label_sw",
        "question",
        "value",
        "display_order",
        "is_active",
    )

    list_filter = (
        "question__section__event_form",
        "is_active",
    )

    search_fields = (
        "label_sw",
        "label_en",
        "value",
        "question__label_sw",
        "question__label_en",
    )


class FormAnswerInline(admin.TabularInline):
    model = FormAnswer
    extra = 0
    can_delete = False

    fields = (
        "question",
        "text_value",
        "number_value",
        "date_value",
        "datetime_value",
        "boolean_value",
        "uploaded_file",
    )

    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(FormSubmission)
class FormSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "reference_number",
        "event_name",
        "form_name",
        "submitter_email",
        "submitter_phone",
        "language",
        "is_complete",
        "review_status_badge",
        "submitted_on",
    )

    list_filter = (
        "event_form__event",
        "event_form",
        "language",
        "is_complete",
        "review_status",
        "created_at",
    )

    search_fields = (
        "reference_number",
        "submitter_email",
        "submitter_phone",
        "event_form__event__code",
        "event_form__event__title_sw",
        "event_form__event__title_en",
    )

    readonly_fields = (
        "reference_number",
        "event_form",
        "submitted_by",
        "language",
        "submitter_email",
        "submitter_phone",
        "ip_address",
        "user_agent",
        "is_complete",
        "reviewed_by",
        "reviewed_at",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    )

    date_hierarchy = "created_at"
    list_per_page = 50
    list_select_related = (
        "event_form",
        "event_form__event",
    )
    actions = (
        "approve_submissions",
        "reject_submissions",
        "reset_submissions_to_pending",
        "export_submissions_csv",
    )

    inlines = [
        FormAnswerInline,
    ]

    def has_add_permission(self, request):
        return False

    @admin.display(description="Event", ordering="event_form__event__code")
    def event_name(self, obj):
        return obj.event_form.event.code

    @admin.display(description="Form", ordering="event_form__name_en")
    def form_name(self, obj):
        return obj.event_form.name_en

    @admin.display(description="Submitted on", ordering="created_at")
    def submitted_on(self, obj):
        return obj.created_at

    @admin.display(description="Review status", ordering="review_status")
    def review_status_badge(self, obj):
        colors = {
            FormSubmission.ReviewStatus.PENDING: ("#854d0e", "#fef9c3"),
            FormSubmission.ReviewStatus.APPROVED: ("#166534", "#dcfce7"),
            FormSubmission.ReviewStatus.REJECTED: ("#991b1b", "#fee2e2"),
        }
        foreground, background = colors[obj.review_status]
        return format_html(
            '<span style="display:inline-block;padding:3px 8px;'
            'border-radius:999px;color:{};background:{};font-weight:700">'
            "{}</span>",
            foreground,
            background,
            obj.get_review_status_display(),
        )

    def save_model(self, request, obj, form, change):
        old_status = None
        if change:
            old_status = (
                FormSubmission.objects
                .filter(pk=obj.pk)
                .values_list("review_status", flat=True)
                .first()
            )

        if obj.review_status != old_status:
            if obj.review_status == FormSubmission.ReviewStatus.PENDING:
                obj.reviewed_by = None
                obj.reviewed_at = None
            else:
                obj.reviewed_by = request.user
                obj.reviewed_at = timezone.now()

        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def _set_review_status(self, request, queryset, status):
        current_time = timezone.now()
        reviewer = (
            request.user
            if status != FormSubmission.ReviewStatus.PENDING
            else None
        )
        reviewed_at = (
            current_time
            if status != FormSubmission.ReviewStatus.PENDING
            else None
        )
        updated = queryset.update(
            review_status=status,
            reviewed_by=reviewer,
            reviewed_at=reviewed_at,
            updated_by=request.user,
            updated_at=current_time,
        )
        self.message_user(
            request,
            f"{updated} submission(s) updated.",
            messages.SUCCESS,
        )

    @admin.action(description="Approve selected submissions")
    def approve_submissions(self, request, queryset):
        self._set_review_status(
            request,
            queryset,
            FormSubmission.ReviewStatus.APPROVED,
        )

    @admin.action(description="Reject selected submissions")
    def reject_submissions(self, request, queryset):
        self._set_review_status(
            request,
            queryset,
            FormSubmission.ReviewStatus.REJECTED,
        )

    @admin.action(description="Reset selected submissions to pending")
    def reset_submissions_to_pending(self, request, queryset):
        self._set_review_status(
            request,
            queryset,
            FormSubmission.ReviewStatus.PENDING,
        )

    @admin.action(description="Export selected submissions to CSV")
    def export_submissions_csv(self, request, queryset):
        submissions = (
            queryset
            .select_related("event_form", "event_form__event")
            .prefetch_related(
                "answers__question",
                "answers__selected_options",
            )
            .order_by("-created_at")
        )
        csv_content = submissions_csv(submissions)
        response = HttpResponse(
            "\ufeff" + csv_content,
            content_type="text/csv; charset=utf-8",
        )
        response["Content-Disposition"] = (
            'attachment; filename="registration-submissions.csv"'
        )
        response["X-Content-Type-Options"] = "nosniff"
        return response


@admin.register(FormAnswer)
class FormAnswerAdmin(admin.ModelAdmin):
    list_display = (
        "submission",
        "question",
        "short_answer",
        "created_at",
    )

    list_filter = (
        "question__question_type",
        "question__section__event_form",
    )

    search_fields = (
        "submission__reference_number",
        "question__label_sw",
        "question__label_en",
        "text_value",
    )

    readonly_fields = (
        "submission",
        "question",
        "text_value",
        "number_value",
        "date_value",
        "datetime_value",
        "boolean_value",
        "uploaded_file",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    )

    def short_answer(self, obj):
        value = (
            obj.text_value
            or obj.number_value
            or obj.date_value
            or obj.datetime_value
            or obj.boolean_value
            or obj.uploaded_file
            or "-"
        )

        return str(value)[:80]

    short_answer.short_description = "Answer"

    def has_add_permission(self, request):
        return False
