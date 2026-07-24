from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    class Role(models.TextChoices):
        SYSTEM_ADMIN = "SYSTEM_ADMIN", _("System Administrator")
        EVENT_ADMIN = "EVENT_ADMIN", _("Event Administrator")
        REGISTRATION_OFFICER = (
            "REGISTRATION_OFFICER",
            _("Registration Officer"),
        )
        ATTENDANCE_OFFICER = (
            "ATTENDANCE_OFFICER",
            _("Attendance Officer"),
        )
        REPORT_OFFICER = "REPORT_OFFICER", _("Report Officer")
        PARTICIPANT = "PARTICIPANT", _("Participant")

    class PreferredLanguage(models.TextChoices):
        SWAHILI = "sw", _("Kiswahili")
        ENGLISH = "en", _("English")

    email = models.EmailField(
        _("email address"),
        unique=True,
    )

    employee_number = models.CharField(
        _("employee number"),
        max_length=50,
        unique=True,
        null=True,
        blank=True,
    )

    phone_number = models.CharField(
        _("phone number"),
        max_length=30,
        blank=True,
    )

    role = models.CharField(
        _("role"),
        max_length=30,
        choices=Role.choices,
        default=Role.PARTICIPANT,
    )

    preferred_language = models.CharField(
        _("preferred language"),
        max_length=5,
        choices=PreferredLanguage.choices,
        default=PreferredLanguage.SWAHILI,
    )

    created_at = models.DateTimeField(
        _("created at"),
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        _("updated at"),
        auto_now=True,
    )

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["first_name", "last_name", "username"]

    def __str__(self):
        full_name = self.get_full_name().strip()
        return full_name or self.username