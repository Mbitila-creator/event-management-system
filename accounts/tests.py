from django.test import TestCase

from .models import User

# Create your tests here.


class RoleAndLanguageTests(TestCase):
    def test_staff_login_page_is_public_and_bilingual_ready(self):
        response = self.client.get("/en/staff/login/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Staff login")
        self.assertContains(response, "Participants do not need a staff account")

    def test_attendance_officer_login_opens_check_in_interface(self):
        User.objects.create_user(
            username="login-attendance",
            email="login-attendance@example.org",
            password="test-password",
            role=User.Role.ATTENDANCE_OFFICER,
            preferred_language="en",
            is_staff=True,
        )

        response = self.client.post(
            "/en/staff/login/",
            {"username": "login-attendance", "password": "test-password"},
        )

        self.assertRedirects(
            response,
            "/en/staff/",
            fetch_redirect_response=False,
        )
        workspace = self.client.get("/en/staff/")
        self.assertRedirects(
            workspace,
            "/en/check-in/",
            fetch_redirect_response=False,
        )

    def test_report_officer_workspace_opens_reports(self):
        user = User.objects.create_user(
            username="login-reporter",
            email="login-reporter@example.org",
            password="test-password",
            role=User.Role.REPORT_OFFICER,
            preferred_language="en",
            is_staff=True,
        )
        self.client.force_login(user)

        response = self.client.get("/en/staff/")

        self.assertRedirects(
            response,
            "/en/reports/attendance/",
            fetch_redirect_response=False,
        )

    def test_event_administrator_workspace_opens_administration(self):
        user = User.objects.create_user(
            username="login-event-admin",
            email="login-event-admin@example.org",
            password="test-password",
            role=User.Role.EVENT_ADMIN,
            preferred_language="en",
            is_staff=True,
        )
        self.client.force_login(user)

        response = self.client.get("/en/staff/")

        self.assertRedirects(
            response,
            "/en/admin/",
            fetch_redirect_response=False,
        )

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
        self.assertContains(response, "Active events")
        self.assertContains(response, "Pending registrations")

    def test_attendance_officer_dashboard_only_shows_attendance_statistics(self):
        user = User.objects.create_user(
            username="attendance-dashboard", email="attendance@example.org",
            role=User.Role.ATTENDANCE_OFFICER,
            preferred_language="en", is_staff=True,
        )
        self.client.force_login(user)
        response = self.client.get("/en/admin/")
        self.assertContains(response, "Participants checked in")
        self.assertNotContains(response, "Pending registrations")
        self.assertNotContains(response, "Payments awaiting verification")


class RoleAccessMatrixTests(TestCase):
    roles = (
        User.Role.SYSTEM_ADMIN,
        User.Role.EVENT_ADMIN,
        User.Role.REGISTRATION_OFFICER,
        User.Role.ATTENDANCE_OFFICER,
        User.Role.REPORT_OFFICER,
        User.Role.PARTICIPANT,
    )

    def setUp(self):
        self.users = {}
        for index, role in enumerate(self.roles):
            self.users[role] = User.objects.create_user(
                username=f"role-{index}",
                email=f"role-{index}@example.org",
                role=role,
                preferred_language="en",
                is_staff=True,
            )

    def assert_role_access(self, path, allowed_roles):
        for role, user in self.users.items():
            with self.subTest(path=path, role=role):
                self.client.force_login(user)
                response = self.client.get(path)
                if role in allowed_roles:
                    self.assertEqual(response.status_code, 200)
                else:
                    self.assertNotEqual(response.status_code, 200)
                self.client.logout()

    def test_administration_dashboard_excludes_participants(self):
        self.assert_role_access(
            "/en/admin/",
            set(self.roles) - {User.Role.PARTICIPANT},
        )

    def test_event_management_access(self):
        self.assert_role_access(
            "/en/admin/events/event/",
            {User.Role.SYSTEM_ADMIN, User.Role.EVENT_ADMIN},
        )

    def test_registration_and_payment_access(self):
        allowed = {
            User.Role.SYSTEM_ADMIN,
            User.Role.EVENT_ADMIN,
            User.Role.REGISTRATION_OFFICER,
            User.Role.REPORT_OFFICER,
        }
        self.assert_role_access(
            "/en/admin/forms_builder/formsubmission/", allowed,
        )
        self.assert_role_access(
            "/en/admin/forms_builder/payment/", allowed,
        )

    def test_check_in_access_does_not_accept_report_officer(self):
        self.assert_role_access(
            "/en/check-in/",
            {
                User.Role.SYSTEM_ADMIN,
                User.Role.EVENT_ADMIN,
                User.Role.REGISTRATION_OFFICER,
                User.Role.ATTENDANCE_OFFICER,
            },
        )

    def test_reports_are_limited_to_report_roles(self):
        allowed = {
            User.Role.SYSTEM_ADMIN,
            User.Role.EVENT_ADMIN,
            User.Role.REPORT_OFFICER,
        }
        self.assert_role_access("/en/reports/attendance/", allowed)
        self.assert_role_access("/en/reports/evaluations/", allowed)
