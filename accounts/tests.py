from django.test import TestCase

from .models import User

# Create your tests here.


class RoleAndLanguageTests(TestCase):
    def test_operational_role_automatically_enables_staff_status(self):
        user = User.objects.create_user(
            username="automatic-staff",
            email="automatic-staff@example.org",
            role=User.Role.ATTENDANCE_OFFICER,
            is_staff=False,
        )

        self.assertTrue(user.is_staff)

    def test_participant_role_does_not_automatically_enable_staff_status(self):
        user = User.objects.create_user(
            username="public-participant",
            email="public-participant@example.org",
            role=User.Role.PARTICIPANT,
            is_staff=False,
        )

        self.assertFalse(user.is_staff)

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

    def test_event_administrator_opens_independent_staff_workspace(self):
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

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Staff workspace")
        self.assertContains(response, "Advanced administration")
        self.assertNotContains(response, "Start typing to filter")

    def test_registration_officer_workspace_has_no_django_admin_sidebar(self):
        user = User.objects.create_user(
            username="workspace-registration",
            email="workspace-registration@example.org",
            password="test-password",
            role=User.Role.REGISTRATION_OFFICER,
            preferred_language="en",
        )
        self.client.force_login(user)

        response = self.client.get("/en/staff/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Registrations awaiting review")
        self.assertNotContains(response, "Site administration")
        self.assertNotContains(response, "Start typing to filter")

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

    def test_staff_workspace_uses_authenticated_users_preferred_language(self):
        user = User.objects.create_user(
            username="swahili-registration",
            email="swahili-registration@example.org",
            role=User.Role.REGISTRATION_OFFICER,
            preferred_language="sw",
        )
        self.client.force_login(user)

        response = self.client.get("/en/staff/")

        self.assertRedirects(response, "/sw/staff/", fetch_redirect_response=False)

        preferred_page = self.client.get("/sw/staff/")
        self.assertEqual(preferred_page.status_code, 200)

        manually_switched = self.client.get("/en/staff/")
        self.assertEqual(manually_switched.status_code, 200)
        self.assertContains(manually_switched, "Staff workspace")

    def test_administration_has_language_switcher(self):
        user = User.objects.create_user(
            username="language-admin",
            email="language-admin@example.org",
            role=User.Role.SYSTEM_ADMIN,
            preferred_language="en",
        )
        self.client.force_login(user)

        response = self.client.get("/en/admin/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="admin-language"')
        self.assertContains(response, 'value="sw"')
        self.assertContains(response, 'value="en"')

        manually_switched = self.client.get("/sw/admin/")
        self.assertEqual(manually_switched.status_code, 200)

    def test_check_in_uses_authenticated_users_preferred_language(self):
        user = User.objects.create_user(
            username="english-attendance",
            email="english-attendance@example.org",
            role=User.Role.ATTENDANCE_OFFICER,
            preferred_language="en",
        )
        self.client.force_login(user)

        response = self.client.get("/sw/check-in/")

        self.assertRedirects(response, "/en/check-in/", fetch_redirect_response=False)

    def test_registration_officer_permissions_are_limited_to_operations(self):
        user = User.objects.create_user(
            username="limited-registration",
            email="limited-registration@example.org",
            role=User.Role.REGISTRATION_OFFICER,
        )

        self.assertTrue(user.has_perm("forms_builder.change_formsubmission"))
        self.assertTrue(user.has_perm("forms_builder.change_payment"))
        self.assertTrue(user.has_perm("checkin.add_participantcheckin"))
        self.assertFalse(user.has_perm("forms_builder.change_eventform"))
        self.assertFalse(user.has_perm("forms_builder.add_formquestion"))
        self.assertFalse(user.has_perm("forms_builder.change_certificaterecord"))
        self.assertFalse(user.has_perm("events.change_event"))

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
        self.assertContains(response, "Create new event")
        self.assertContains(response, "/en/admin/events/event/add/")
        self.assertContains(response, "Manage users and passwords")
        self.assertContains(response, "/en/admin/accounts/user/")

    def test_user_list_provides_direct_password_reset_links(self):
        administrator = User.objects.create_user(
            username="password-administrator",
            email="password-administrator@example.org",
            password="test-password",
            role=User.Role.SYSTEM_ADMIN,
            preferred_language="en",
        )
        target = User.objects.create_user(
            username="password-target",
            email="password-target@example.org",
            password="old-password",
            role=User.Role.ATTENDANCE_OFFICER,
        )
        self.client.force_login(administrator)

        response = self.client.get("/en/admin/accounts/user/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reset password")
        self.assertContains(
            response,
            f"/en/admin/accounts/user/{target.pk}/password/",
        )

    def test_superuser_dashboard_displays_system_administrator_role(self):
        user = User.objects.create_superuser(
            username="root-dashboard",
            email="root-dashboard@example.org",
            password="test-password",
            preferred_language="en",
        )
        self.client.force_login(user)

        response = self.client.get("/en/admin/")

        self.assertContains(response, "System Administrator")
        self.assertNotContains(response, "<span>Participant</span>", html=True)

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
