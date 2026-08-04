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

    ROLE_PERMISSION_APPS = {
        Role.SYSTEM_ADMIN: {"*"},
        Role.EVENT_ADMIN: {"events", "forms_builder", "checkin", "core"},
        Role.REGISTRATION_OFFICER: {"forms_builder"},
        Role.ATTENDANCE_OFFICER: {"checkin"},
        Role.REPORT_OFFICER: {"forms_builder", "checkin"},
        Role.PARTICIPANT: set(),
    }

    def has_perm(self, perm, obj=None):
        if not self.is_active:
            return False
        if self.is_superuser:
            return True
        app_label = perm.partition(".")[0]
        allowed = self.ROLE_PERMISSION_APPS.get(self.role, set())
        codename = perm.partition(".")[2]
        if self.role == self.Role.REPORT_OFFICER:
            return app_label in allowed and codename.startswith("view_")
        if "*" in allowed or app_label in allowed:
            return True
        return super().has_perm(perm, obj=obj)

    def has_module_perms(self, app_label):
        if not self.is_active:
            return False
        if self.is_superuser:
            return True
        allowed = self.ROLE_PERMISSION_APPS.get(self.role, set())
        return "*" in allowed or app_label in allowed
