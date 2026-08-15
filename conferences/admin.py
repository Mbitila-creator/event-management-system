from django.contrib import admin

from .models import (
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
