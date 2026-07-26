from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from events.models import Event, EventCategory
from forms_builder.models import EventForm, FormSubmission

from .models import ParticipantCheckIn


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
        )
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
        self.assertIn("/admin/login/", response["Location"])

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

    def test_pending_participant_cannot_be_checked_in(self):
        self.client.force_login(self.officer)
        self.submission.review_status = FormSubmission.ReviewStatus.PENDING
        self.submission.save(update_fields=["review_status"])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)
        self.assertFalse(ParticipantCheckIn.objects.exists())

    def test_reference_lookup_redirects_to_participant(self):
        self.client.force_login(self.officer)

        response = self.client.post(
            "/en/check-in/",
            {"identifier": self.submission.reference_number},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self.url)
