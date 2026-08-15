from django.contrib import admin

from .models import ConferenceSession, ConferenceSessionAttendance


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
