from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from events.models import Event, EventCategory
from forms_builder.models import EventForm, FormSubmission, NotificationLog

from .models import ParticipantCheckIn


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
)
class ParticipantCheckInTests(TestCase):
    def setUp(self):
        self.officer = get_user_model().objects.create_user(
            username="attendance-officer",
            email="officer@example.org",
            password="test-password",
            role=User.Role.ATTENDANCE_OFFICER,
        )
        self.participant_user = get_user_model().objects.create_user(
            username="ordinary-participant",
            email="ordinary@example.org",
            password="test-password",
            role=User.Role.PARTICIPANT,
        )
        self.report_officer = get_user_model().objects.create_user(
            username="report-officer",
            email="reports@example.org",
            password="test-password",
            role=User.Role.REPORT_OFFICER,
            is_staff=True,
        )
        category = EventCategory.objects.create(
            name_sw="Maonesho",
            name_en="Exhibition",
            code="EXPO",
        )
        starts_at = timezone.now() + timedelta(days=15)
        event = Event.objects.create(
            category=category,
            code="CHECKIN-2026",
            title_sw="Tukio la Mahudhurio",
            title_en="Check-in Event",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(days=1),
            qr_checkin_enabled=True,
            certificate_enabled=True,
        )
        self.event = event
        event_form = EventForm.objects.create(
            event=event,
            name_sw="Fomu ya Usajili",
            name_en="Registration Form",
            is_published=True,
        )
        self.submission = FormSubmission.objects.create(
            event_form=event_form,
            submitter_email="approved@example.org",
            review_status=FormSubmission.ReviewStatus.APPROVED,
            reviewed_by=self.officer,
            reviewed_at=timezone.now(),
            badge_name="Neema Maarifa",
        )
        self.url = (
            f"/en/check-in/{self.submission.participant_token}/"
        )

    def test_participant_role_cannot_access_check_in(self):
        self.client.force_login(self.participant_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/staff/login/", response["Location"])

    def test_attendance_officer_can_check_in_approved_participant(self):
        self.client.force_login(self.officer)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Participant checked in successfully.")
        check_in = ParticipantCheckIn.objects.get(
            submission=self.submission
        )
        self.assertEqual(check_in.checked_in_by, self.officer)
        self.assertEqual(check_in.method, ParticipantCheckIn.Method.QR)

    def test_repeated_scan_does_not_create_duplicate_check_in(self):
        self.client.force_login(self.officer)

        self.client.post(self.url)
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "This participant is already checked in.",
        )
        self.assertEqual(ParticipantCheckIn.objects.count(), 1)
        self.assertEqual(
            NotificationLog.objects.filter(
                submission=self.submission,
                notification_type=(
                    NotificationLog.NotificationType.CHECK_IN_CONFIRMED
                ),
            ).count(),
            1,
        )

    def test_pending_participant_cannot_be_checked_in(self):
        self.client.force_login(self.officer)
        self.submission.review_status = FormSubmission.ReviewStatus.PENDING
        self.submission.save(update_fields=["review_status"])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Check-in not allowed")
        self.assertFalse(ParticipantCheckIn.objects.exists())

    def test_scan_url_checks_in_immediately(self):
        self.client.force_login(self.officer)

        response = self.client.get(f"{self.url}?auto=1")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Participant checked in successfully.")
        self.assertNotContains(response, 'id="automatic-check-in-form"')
        self.assertTrue(
            ParticipantCheckIn.objects.filter(
                submission=self.submission,
                checked_in_by=self.officer,
            ).exists()
        )

    def test_reference_lookup_redirects_to_participant(self):
        self.client.force_login(self.officer)

        response = self.client.post(
            "/en/check-in/",
            {"identifier": self.submission.reference_number},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self.url)

    def test_report_officer_can_view_attendance_report(self):
        ParticipantCheckIn.objects.create(
            submission=self.submission,
            checked_in_by=self.officer,
        )
        self.client.force_login(self.report_officer)

        response = self.client.get(
            "/en/reports/attendance/",
            {"event": self.event.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Attendance and certificate reports")
        self.assertContains(response, "Neema Maarifa")
        self.assertContains(response, "100.0%")
        self.assertContains(response, "Download certificate CSV")

    def test_attendance_officer_cannot_view_management_reports(self):
        self.client.force_login(self.officer)

        response = self.client.get(
            "/en/reports/attendance/",
            {"event": self.event.pk},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/staff/login/", response["Location"])

    def test_certificate_report_csv_is_downloadable_and_safe(self):
        self.submission.badge_name = "=Unsafe Name"
        self.submission.certificate_authorized = True
        self.submission.certificate_authorized_by = self.report_officer
        self.submission.certificate_authorized_at = timezone.now()
        self.submission.save(update_fields=[
            "badge_name",
            "certificate_authorized",
            "certificate_authorized_by",
            "certificate_authorized_at",
        ])
        ParticipantCheckIn.objects.create(
            submission=self.submission,
            checked_in_by=self.officer,
        )
        self.client.force_login(self.report_officer)

        response = self.client.get(
            "/en/reports/attendance/export/",
            {"event": self.event.pk, "report": "certificates"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        content = response.content.decode("utf-8-sig")
        self.assertIn("Certificate number", content)
        self.assertIn("'=Unsafe Name", content)
        self.assertIn("CERT-", content)

    def test_report_cards_filter_participant_rows(self):
        pending_submission = FormSubmission.objects.create(
            event_form=self.submission.event_form,
            submitter_email="pending@example.org",
            badge_name="Pending Person",
            review_status=FormSubmission.ReviewStatus.PENDING,
        )
        ParticipantCheckIn.objects.create(
            submission=self.submission,
            checked_in_by=self.officer,
        )
        self.client.force_login(self.report_officer)

        checked_response = self.client.get(
            "/en/reports/attendance/",
            {"event": self.event.pk, "filter": "checked_in"},
        )
        self.assertEqual(checked_response.status_code, 200)
        self.assertContains(checked_response, "Neema Maarifa")
        self.assertNotContains(checked_response, "Pending Person")
        self.assertContains(checked_response, "Filtered participants: 1")

        pending_response = self.client.get(
            "/en/reports/attendance/",
            {"event": self.event.pk, "filter": "pending"},
        )
        self.assertContains(pending_response, pending_submission.badge_name)
        self.assertNotContains(pending_response, "Neema Maarifa")

        all_response = self.client.get(
            "/en/reports/attendance/",
            {"event": self.event.pk, "filter": "all"},
        )
        self.assertContains(all_response, "Neema Maarifa")
        self.assertContains(all_response, "Pending Person")

    def test_evaluation_responses_do_not_change_participant_reports(self):
        evaluation_form = EventForm.objects.create(
            event=self.event,
            name_sw="Tathmini ya Wageni",
            name_en="Visitor Evaluation",
            form_type=EventForm.FormType.EVALUATION,
            is_published=True,
        )
        FormSubmission.objects.create(
            event_form=evaluation_form,
            badge_name="Visitor Feedback",
        )
        self.client.force_login(self.report_officer)

        response = self.client.get(
            "/en/reports/attendance/",
            {"event": self.event.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["summary"]["registered"], 1)
        self.assertNotContains(response, "Visitor Feedback")

    def test_checked_in_participant_receives_evaluation_link(self):
        self.event.evaluation_enabled = True
        self.event.save(update_fields=["evaluation_enabled"])
        evaluation_form = EventForm.objects.create(
            event=self.event,
            name_sw="Tathmini ya Tukio",
            name_en="Event Evaluation",
            form_type=EventForm.FormType.EVALUATION,
            is_published=True,
        )
        self.client.force_login(self.officer)

        response = self.client.get(f"{self.url}?auto=1")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Submit event evaluation")
        self.assertContains(
            response,
            f"/en/events/{self.event.slug}/forms/{evaluation_form.slug}/",
        )
