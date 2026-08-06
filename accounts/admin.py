from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import User


def event_admin_permission(request):
    """Permit system administrators and read-only directors into administration."""
    return bool(
        request.user.is_active
        and request.user.is_staff
        and (
            request.user.is_superuser
            or request.user.role in {
                User.Role.SYSTEM_ADMIN,
                User.Role.DIRECTOR,
                User.Role.ASSISTANT_DIRECTOR,
            }
        )
    )


admin.site.has_permission = event_admin_permission


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "employee_number",
        "phone_number",
        "role",
        "preferred_language",
        "is_active",
        "is_staff",
        "password_reset_link",
    )

    list_filter = (
        "role",
        "preferred_language",
        "is_active",
        "is_staff",
        "is_superuser",
    )

    search_fields = (
        "username",
        "email",
        "first_name",
        "last_name",
        "employee_number",
        "phone_number",
    )

    ordering = (
        "first_name",
        "last_name",
        "username",
    )

    fieldsets = UserAdmin.fieldsets + (
        (
            "Event Management Information",
            {
                "fields": (
                    "employee_number",
                    "phone_number",
                    "role",
                    "preferred_language",
                )
            },
        ),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            "Event Management Information",
            {
                "fields": (
                    "email",
                    "first_name",
                    "last_name",
                    "employee_number",
                    "phone_number",
                    "role",
                    "preferred_language",
                )
            },
        ),
    )

    @admin.display(description=_("Password"))
    def password_reset_link(self, obj):
        if not obj.pk:
            return "—"
        url = reverse("admin:auth_user_password_change", args=[obj.pk])
        return format_html(
            '<a class="button" href="{}">{}</a>',
            url,
            _("Reset password"),
        )

    def get_list_display(self, request):
        fields = list(super().get_list_display(request))
        if request.user.role in {
            User.Role.DIRECTOR,
            User.Role.ASSISTANT_DIRECTOR,
        }:
            fields.remove("password_reset_link")
        return fields
