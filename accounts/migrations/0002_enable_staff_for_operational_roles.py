from django.db import migrations


OPERATIONAL_ROLES = (
    "SYSTEM_ADMIN",
    "EVENT_ADMIN",
    "REGISTRATION_OFFICER",
    "ATTENDANCE_OFFICER",
    "REPORT_OFFICER",
)


def enable_operational_staff(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(role__in=OPERATIONAL_ROLES).update(is_staff=True)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]

    operations = [migrations.RunPython(enable_operational_staff, migrations.RunPython.noop)]
