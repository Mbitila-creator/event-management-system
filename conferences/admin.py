from django.contrib import admin

from .models import (
    ConferenceCallForPapers,
    ConferencePaper,
    ConferencePaperReview,
    ConferenceProgrammeContributor,
    ConferenceProgrammeItem,
    ConferenceSession,
    ConferenceSessionAttendance,
    ConferenceSpeaker,
)


class AuditAdminMixin:
    readonly_fields = ("created_by", "updated_by", "created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        if not obj.pk or not obj.created_by:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ConferenceSession)
class ConferenceSessionAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = ("code", "title", "event", "starts_at", "ends_at", "is_active")
    list_filter = ("event", "is_active")
    search_fields = ("code", "title", "event__code", "event__title_en")
    ordering = ("event", "starts_at", "display_order")


@admin.register(ConferenceSessionAttendance)
class ConferenceSessionAttendanceAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = (
        "submission",
        "session",
        "checked_in_at",
        "checked_in_by",
        "method",
    )
    list_filter = ("session__event", "session", "method", "checked_in_at")
    search_fields = (
        "submission__reference_number",
        "submission__badge_name",
        "submission__badge_organization",
    )
    autocomplete_fields = ("submission", "session", "checked_in_by")
    readonly_fields = AuditAdminMixin.readonly_fields + ("checked_in_at",)


class ConferenceProgrammeContributorInline(admin.TabularInline):
    model = ConferenceProgrammeContributor
    extra = 1
    autocomplete_fields = ("speaker",)
    fields = ("speaker", "role", "display_order", "is_active")


@admin.register(ConferenceSpeaker)
class ConferenceSpeakerAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = (
        "full_name",
        "position_title",
        "institution",
        "event",
        "is_active",
    )
    list_filter = ("event", "is_active")
    search_fields = (
        "full_name",
        "position_title",
        "institution",
        "event__code",
    )
    ordering = ("event", "display_order", "full_name")


@admin.register(ConferenceProgrammeItem)
class ConferenceProgrammeItemAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = (
        "code",
        "title",
        "session",
        "item_type",
        "starts_at",
        "ends_at",
        "is_published",
        "is_active",
    )
    list_filter = (
        "session__event",
        "session",
        "item_type",
        "is_published",
        "is_active",
    )
    search_fields = (
        "code",
        "title",
        "description",
        "session__title",
        "session__event__code",
    )
    ordering = ("session__event", "starts_at", "display_order")
    inlines = (ConferenceProgrammeContributorInline,)


@admin.register(ConferenceProgrammeContributor)
class ConferenceProgrammeContributorAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = ("speaker", "programme_item", "role", "is_active")
    list_filter = ("programme_item__session__event", "role", "is_active")
    search_fields = (
        "speaker__full_name",
        "programme_item__title",
        "programme_item__session__event__code",
    )
    autocomplete_fields = ("speaker", "programme_item")


@admin.register(ConferenceCallForPapers)
class ConferenceCallForPapersAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = ("title", "event", "opens_at", "closes_at", "is_published")
    list_filter = ("is_published", "event")
    search_fields = ("title", "event__code", "event__title_en")


class ConferencePaperReviewInline(admin.TabularInline):
    model = ConferencePaperReview
    extra = 0
    readonly_fields = (
        "decision", "message_to_author", "internal_notes", "assigned_session",
        "reviewer", "created_at",
    )
    fields = readonly_fields
    can_delete = False


@admin.register(ConferencePaper)
class ConferencePaperAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = (
        "reference_number", "title", "corresponding_author", "submission_type",
        "status", "assigned_session", "created_at",
    )
    list_filter = ("call__event", "status", "submission_type", "presentation_format")
    search_fields = (
        "reference_number", "title", "corresponding_author", "institution", "email",
    )
    readonly_fields = AuditAdminMixin.readonly_fields + (
        "public_token", "reference_number", "reviewed_by", "reviewed_at",
    )
    autocomplete_fields = ("assigned_session",)
    inlines = (ConferencePaperReviewInline,)


@admin.register(ConferencePaperReview)
class ConferencePaperReviewAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = ("paper", "decision", "reviewer", "assigned_session", "created_at")
    list_filter = ("decision", "paper__call__event")
    search_fields = ("paper__reference_number", "paper__title", "reviewer__username")
    autocomplete_fields = ("paper", "assigned_session", "reviewer")
