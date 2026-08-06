from datetime import timedelta

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

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
        self.assertContains(response, "Certificate authorization")
        self.assertContains(response, "Attendance reports")
        self.assertContains(response, "Evaluation reports")
        self.assertNotContains(response, "Advanced administration")
        self.assertNotContains(response, "Start typing to filter")

        administration = self.client.get("/en/admin/")
        self.assertRedirects(
            administration,
            "/en/staff/",
            fetch_redirect_response=False,
        )

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


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class EventAdministratorOperationsTests(TestCase):
    def setUp(self):
        from events.models import Event, EventCategory
        from forms_builder.models import EventForm, FormSubmission, Payment

        self.event_admin = User.objects.create_user(
            username="event-operations",
            email="event-operations@example.org",
            role=User.Role.EVENT_ADMIN,
            preferred_language="en",
        )
        category = EventCategory.objects.create(
            name_sw="Maonesho", name_en="Exhibition", code="EXHIBITION",
        )
        start = timezone.now() + timedelta(days=10)
        event = Event.objects.create(
            category=category,
            code="OPERATIONS-2026",
            title_sw="Tukio la Uendeshaji",
            title_en="Operations Event",
            starts_at=start,
            ends_at=start + timedelta(days=2),
            certificate_enabled=True,
            booth_enabled=True,
        )
        event_form = EventForm.objects.create(
            event=event,
            name_sw="Fomu ya Usajili",
            name_en="Registration Form",
            is_published=True,
        )
        self.submission = FormSubmission.objects.create(
            event_form=event_form,
            submitter_email="participant@example.org",
            badge_name="Test Participant",
            language="en",
        )
        self.payment = Payment.objects.create(
            submission=self.submission,
            amount="2000000.00",
            transaction_reference="OPERATIONS-PAYMENT-1",
        )
        from forms_builder.models import Booth
        self.booth = Booth.objects.create(
            event=event,
            code="A-01",
            name_sw="Banda A-01",
            name_en="Booth A-01",
            zone_sw="Eneo A",
            zone_en="Zone A",
        )
        self.client.force_login(self.event_admin)

    def test_event_administrator_can_approve_registration_and_verify_payment(self):
        from forms_builder.models import FormSubmission, Payment

        response = self.client.post(
            f"/en/staff/registrations/{self.submission.pk}/approve/",
        )
        self.assertRedirects(response, "/en/staff/", fetch_redirect_response=False)
        self.submission.refresh_from_db()
        self.assertEqual(
            self.submission.review_status,
            FormSubmission.ReviewStatus.APPROVED,
        )
        self.assertEqual(self.submission.reviewed_by, self.event_admin)

        response = self.client.post(
            f"/en/staff/payments/{self.payment.pk}/verify/",
        )
        self.assertRedirects(response, "/en/staff/", fetch_redirect_response=False)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.VERIFIED)
        self.assertEqual(self.payment.verified_by, self.event_admin)

    def test_event_administrator_can_review_participant_and_payment_details(self):
        workspace = self.client.get("/en/staff/")
        detail_url = (
            f"/en/staff/participants/{self.submission.pk}/review/"
        )
        self.assertContains(workspace, detail_url)

        details = self.client.get(detail_url)
        self.assertEqual(details.status_code, 200)
        self.assertContains(details, "Participant contact information")
        self.assertContains(details, "participant@example.org")
        self.assertContains(details, "OPERATIONS-PAYMENT-1")
        self.assertContains(details, "Approve registration")
        self.assertContains(details, "Verify payment")

        participant = User.objects.create_user(
            username="participant-no-review",
            email="participant-no-review@example.org",
            role=User.Role.PARTICIPANT,
            preferred_language="en",
        )
        self.client.force_login(participant)
        forbidden = self.client.get(detail_url)
        self.assertEqual(forbidden.status_code, 403)

    def test_workspace_statistic_cards_filter_to_matching_lists(self):
        workspace = self.client.get("/en/staff/")
        self.assertContains(workspace, "?view=events#active-events")
        self.assertContains(workspace, "?view=registrations#registrations")
        self.assertContains(workspace, "?view=payments#payments")
        self.assertContains(workspace, "?view=checkins#checked-in")

        events_view = self.client.get("/en/staff/?view=events")
        self.assertEqual(events_view.context["selected_view"], "events")
        self.assertContains(events_view, 'id="active-events"')
        self.assertNotContains(events_view, 'id="registrations"')

        payments_view = self.client.get("/en/staff/?view=payments")
        self.assertContains(payments_view, 'id="payments"')
        self.assertNotContains(payments_view, 'id="registrations"')

    def test_event_administrator_can_assign_ready_and_release_booth(self):
        from forms_builder.models import Booth, FormSubmission

        self.submission.review_status = FormSubmission.ReviewStatus.APPROVED
        self.submission.save(update_fields=("review_status", "updated_at"))

        page = self.client.get("/en/staff/booths/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Booth assignments")
        self.assertContains(page, self.submission.reference_number)

        response = self.client.post(
            f"/en/staff/booths/{self.booth.pk}/update/",
            {"action": "assign", "submission_id": self.submission.pk},
        )
        self.assertRedirects(
            response,
            f"/en/staff/booths/?event={self.booth.event_id}",
            fetch_redirect_response=False,
        )
        self.booth.refresh_from_db()
        self.assertEqual(self.booth.assigned_submission, self.submission)
        self.assertEqual(self.booth.status, Booth.Status.ASSIGNED)
        self.assertEqual(self.booth.updated_by, self.event_admin)

        self.client.post(
            f"/en/staff/booths/{self.booth.pk}/update/",
            {"action": "ready"},
        )
        self.booth.refresh_from_db()
        self.assertEqual(self.booth.status, Booth.Status.READY)

        self.client.post(
            f"/en/staff/booths/{self.booth.pk}/update/",
            {"action": "release"},
        )
        self.booth.refresh_from_db()
        self.assertIsNone(self.booth.assigned_submission)
        self.assertEqual(self.booth.status, Booth.Status.UNASSIGNED)

    def test_registration_officer_cannot_open_booth_assignment_workspace(self):
        officer = User.objects.create_user(
            username="registration-no-booths",
            email="registration-no-booths@example.org",
            role=User.Role.REGISTRATION_OFFICER,
            preferred_language="en",
        )
        self.client.force_login(officer)
        response = self.client.get("/en/staff/booths/")
        self.assertEqual(response.status_code, 403)

    def test_event_administrator_can_authorize_checked_in_certificate(self):
        from checkin.models import ParticipantCheckIn
        from forms_builder.models import CertificateRecord, FormSubmission

        self.submission.review_status = FormSubmission.ReviewStatus.APPROVED
        self.submission.save(update_fields=("review_status", "updated_at"))
        ParticipantCheckIn.objects.create(
            submission=self.submission,
            checked_in_by=self.event_admin,
        )
        response = self.client.post(
            f"/en/staff/certificates/{self.submission.pk}/authorize/",
        )
        self.assertRedirects(response, "/en/staff/", fetch_redirect_response=False)
        certificate = CertificateRecord.objects.get(submission=self.submission)
        self.assertEqual(certificate.status, CertificateRecord.Status.AUTHORIZED)
        self.assertEqual(certificate.authorized_by, self.event_admin)

    def test_rejection_and_certificate_denial_require_and_store_reasons(self):
        from checkin.models import ParticipantCheckIn
        from forms_builder.models import CertificateRecord, FormSubmission, Payment

        missing_reason = self.client.post(
            f"/en/staff/payments/{self.payment.pk}/reject/",
        )
        self.assertRedirects(
            missing_reason, "/en/staff/", fetch_redirect_response=False,
        )
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)

        self.client.post(
            f"/en/staff/payments/{self.payment.pk}/reject/",
            {"reason": "The transaction reference could not be confirmed."},
        )
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.REJECTED)
        self.assertEqual(
            self.payment.notes,
            "The transaction reference could not be confirmed.",
        )

        self.submission.review_status = FormSubmission.ReviewStatus.APPROVED
        self.submission.save(update_fields=("review_status", "updated_at"))
        ParticipantCheckIn.objects.create(
            submission=self.submission,
            checked_in_by=self.event_admin,
        )
        self.client.post(
            f"/en/staff/certificates/{self.submission.pk}/deny/",
            {"reason": "The minimum attendance requirement was not met."},
        )
        certificate = CertificateRecord.objects.get(submission=self.submission)
        self.assertEqual(certificate.status, CertificateRecord.Status.DENIED)
        self.assertEqual(
            certificate.denial_reason,
            "The minimum attendance requirement was not met.",
        )
        self.assertEqual(certificate.denied_by, self.event_admin)

        participant_page = self.client.get(
            f"/en/participants/{self.submission.participant_token}/",
        )
        self.assertContains(participant_page, "Certificate not authorized")
        self.assertContains(
            participant_page,
            "The minimum attendance requirement was not met.",
        )

        from forms_builder.models import NotificationLog
        self.assertTrue(NotificationLog.objects.filter(
            submission=self.submission,
            notification_type=NotificationLog.NotificationType.CERTIFICATE_DENIED,
        ).exists())
        denial_email = next(
            message for message in mail.outbox
            if "Certificate decision" in message.subject
        )
        self.assertIn("View certificate status:", denial_email.body)
        self.assertIn(
            f"/en/participants/{self.submission.participant_token}/",
            denial_email.body,
        )
        self.assertIn(
            "The minimum attendance requirement was not met.",
            denial_email.body,
        )

        workspace = self.client.get("/en/staff/")
        self.assertEqual(workspace.context["certificate_candidate_count"], 0)
        self.assertContains(workspace, "View details")
        self.assertContains(
            workspace,
            "The minimum attendance requirement was not met.",
        )

    def test_registration_officer_cannot_authorize_certificate(self):
        officer = User.objects.create_user(
            username="registration-no-certificate",
            email="registration-no-certificate@example.org",
            role=User.Role.REGISTRATION_OFFICER,
        )
        self.client.force_login(officer)
        response = self.client.post(
            f"/en/staff/certificates/{self.submission.pk}/authorize/",
        )
        self.assertEqual(response.status_code, 403)


class RoleAndLanguageContinuationTests(TestCase):
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

    def test_attendance_officer_is_kept_out_of_system_administration(self):
        user = User.objects.create_user(
            username="attendance-dashboard", email="attendance@example.org",
            role=User.Role.ATTENDANCE_OFFICER,
            preferred_language="en", is_staff=True,
        )
        self.client.force_login(user)
        response = self.client.get("/en/admin/")
        self.assertRedirects(
            response,
            "/en/staff/",
            fetch_redirect_response=False,
        )


class RoleAccessMatrixTests(TestCase):
    roles = (
        User.Role.SYSTEM_ADMIN,
        User.Role.EVENT_ADMIN,
        User.Role.REGISTRATION_OFFICER,
        User.Role.ATTENDANCE_OFFICER,
        User.Role.REPORT_OFFICER,
        User.Role.DIRECTOR,
        User.Role.ASSISTANT_DIRECTOR,
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

    def test_system_administration_is_reserved_for_system_administrator(self):
        self.assert_role_access(
            "/en/admin/",
            {
                User.Role.SYSTEM_ADMIN,
                User.Role.DIRECTOR,
                User.Role.ASSISTANT_DIRECTOR,
            },
        )

    def test_event_management_access(self):
        self.assert_role_access(
            "/en/admin/events/event/",
            {
                User.Role.SYSTEM_ADMIN,
                User.Role.DIRECTOR,
                User.Role.ASSISTANT_DIRECTOR,
            },
        )

    def test_registration_and_payment_access(self):
        allowed = {
            User.Role.SYSTEM_ADMIN,
            User.Role.DIRECTOR,
            User.Role.ASSISTANT_DIRECTOR,
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
            User.Role.DIRECTOR,
            User.Role.ASSISTANT_DIRECTOR,
        }
        self.assert_role_access("/en/reports/attendance/", allowed)
        self.assert_role_access("/en/reports/evaluations/", allowed)

    def test_directors_have_system_wide_view_permissions_only(self):
        view_permissions = {
            "accounts.view_user",
            "core.view_region",
            "events.view_event",
            "forms_builder.view_formsubmission",
            "forms_builder.view_payment",
            "forms_builder.view_certificaterecord",
            "checkin.view_participantcheckin",
        }
        forbidden_permissions = {
            "accounts.change_user",
            "events.add_event",
            "events.change_event",
            "events.delete_event",
            "forms_builder.change_formsubmission",
            "forms_builder.change_payment",
            "forms_builder.change_certificaterecord",
            "checkin.add_participantcheckin",
            "checkin.change_participantcheckin",
            "checkin.delete_participantcheckin",
        }
        for role in {User.Role.DIRECTOR, User.Role.ASSISTANT_DIRECTOR}:
            executive = self.users[role]
            self.assertTrue(executive.is_staff)
            for permission in view_permissions:
                with self.subTest(role=role, permission=permission):
                    self.assertTrue(executive.has_perm(permission))
            for permission in forbidden_permissions:
                with self.subTest(role=role, permission=permission):
                    self.assertFalse(executive.has_perm(permission))

            self.client.force_login(executive)
            dashboard = self.client.get("/en/admin/")
            self.assertEqual(dashboard.status_code, 200)
            self.assertNotContains(dashboard, "Check-in Participants")
            self.assertNotContains(dashboard, "Manage users and reset passwords")

            user_details = self.client.get(
                f"/en/admin/accounts/user/{executive.pk}/change/",
            )
            self.assertEqual(user_details.status_code, 200)
            self.assertNotContains(user_details, 'name="_save"')
            self.assertEqual(
                self.client.post(
                    f"/en/admin/accounts/user/{executive.pk}/change/",
                    {"username": "unauthorized-change"},
                ).status_code,
                403,
            )
            self.client.logout()

    def test_directors_cannot_use_operational_endpoints(self):
        paths = (
            "/en/staff/registrations/999/approve/",
            "/en/staff/payments/999/verify/",
            "/en/staff/certificates/999/authorize/",
            "/en/staff/booths/999/update/",
        )
        for role in {User.Role.DIRECTOR, User.Role.ASSISTANT_DIRECTOR}:
            self.client.force_login(self.users[role])
            for path in paths:
                with self.subTest(role=role, path=path):
                    self.assertEqual(self.client.post(path).status_code, 403)
            self.client.logout()
