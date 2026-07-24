from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


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