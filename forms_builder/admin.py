from django.contrib import admin

from .models import (
    EventForm,
    FormAnswer,
    FormQuestion,
    FormSection,
    FormSubmission,
    QuestionOption,
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
    )

    inlines = [
        FormSectionInline,
    ]


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
        "event_form",
        "submitter_email",
        "submitter_phone",
        "language",
        "is_complete",
        "created_at",
    )

    list_filter = (
        "event_form__event",
        "event_form",
        "language",
        "is_complete",
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
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    )

    date_hierarchy = "created_at"

    inlines = [
        FormAnswerInline,
    ]

    def has_add_permission(self, request):
        return False


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
