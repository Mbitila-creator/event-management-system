from django.test import TestCase

from .models import User

# Create your tests here.


class RoleAndLanguageTests(TestCase):
    def test_report_officer_has_view_but_not_change_permission(self):
        user = User.objects.create_user(
            username="reporter", email="reporter@example.org",
            role=User.Role.REPORT_OFFICER,
        )
        self.assertTrue(user.has_perm("forms_builder.view_formsubmission"))
        self.assertFalse(user.has_perm("forms_builder.change_formsubmission"))

    def test_admin_uses_authenticated_users_preferred_language(self):
        user = User.objects.create_user(
            username="english-admin", email="english@example.org",
            role=User.Role.SYSTEM_ADMIN, preferred_language="en", is_staff=True,
        )
        self.client.force_login(user)
        response = self.client.get("/sw/admin/")
        self.assertRedirects(response, "/en/admin/", fetch_redirect_response=False)

    def test_system_administrator_sees_operational_dashboard(self):
        user = User.objects.create_user(
            username="system-admin", email="system@example.org",
            role=User.Role.SYSTEM_ADMIN, preferred_language="en", is_staff=True,
        )
        self.client.force_login(user)
        response = self.client.get("/en/admin/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reference Data")
        self.assertContains(response, "Payments")
        self.assertContains(response, "Participants and Certificates")
