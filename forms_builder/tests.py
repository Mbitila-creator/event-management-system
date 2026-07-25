from django.test import TestCase

# Create your tests here.
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import (
    RequestFactory,
    SimpleTestCase,
    TestCase,
    override_settings,
)
from django.utils import timezone

from events.models import Event, EventCategory

from .admin import FormSubmissionAdmin
from .models import EventForm, FormSubmission

from .services import (
    generate_qr_png,
    public_form_path,
    public_form_url,
    safe_spreadsheet_value,
)


class PublicFormServiceTests(SimpleTestCase):
    def setUp(self):
        self.event_form = SimpleNamespace(
            event=SimpleNamespace(slug="education-week"),
            slug="participant-registration",
        )

    def test_public_form_path_contains_selected_language(self):
        path = public_form_path(self.event_form, language="en")

        self.assertEqual(
            path,
            (
                "/en/events/education-week/forms/"
                "participant-registration/"
            ),
        )

    @override_settings(PUBLIC_BASE_URL="https://events.example.org")
    def test_configured_public_base_url_is_used(self):
        url = public_form_url(self.event_form, language="sw")

        self.assertEqual(
            url,
            (
                "https://events.example.org/sw/events/"
                "education-week/forms/participant-registration/"
            ),
        )

    @override_settings(PUBLIC_BASE_URL="")
    def test_request_address_is_used_during_local_development(self):
        request = RequestFactory().get(
            "/",
            HTTP_HOST="192.168.1.25:8000",
        )

        url = public_form_url(
            self.event_form,
            request=request,
            language="sw",
        )

        self.assertEqual(
            url,
            (
                "http://192.168.1.25:8000/sw/events/"
                "education-week/forms/participant-registration/"
            ),
        )

    def test_generated_qr_is_a_png(self):
        image_data = generate_qr_png("https://example.org/register/")

        self.assertTrue(image_data.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_spreadsheet_formula_values_are_escaped(self):
        self.assertEqual(
            safe_spreadsheet_value('=HYPERLINK("bad")'),
            "'=HYPERLINK(\"bad\")",
        )
        self.assertEqual(
            safe_spreadsheet_value("  +SUM(1,2)"),
            "'  +SUM(1,2)",
        )

    def test_normal_spreadsheet_values_are_unchanged(self):
        self.assertEqual(
            safe_spreadsheet_value("Participant name"),
            "Participant name",
        )


class SubmissionReviewAdminTests(TestCase):
    def setUp(self):
        self.reviewer = get_user_model().objects.create_user(
            username="reviewer",
            email="reviewer@example.org",
            password="test-password",
            is_staff=True,
        )
        category = EventCategory.objects.create(
            name_sw="Mkutano",
            name_en="Conference",
            code="CONF",
        )
        starts_at = timezone.now() + timedelta(days=30)
        event = Event.objects.create(
            category=category,
            code="TEST-2026",
            title_sw="Tukio la Majaribio",
            title_en="Test Event",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(days=1),
        )
        event_form = EventForm.objects.create(
            event=event,
            name_sw="Fomu ya Majaribio",
            name_en="Test Form",
            is_published=True,
        )
        self.submission = FormSubmission.objects.create(
            event_form=event_form,
            submitter_email="participant@example.org",
        )
        self.model_admin = FormSubmissionAdmin(
            FormSubmission,
            admin.site,
        )
        self.model_admin.message_user = Mock()
        self.request = RequestFactory().post("/admin/")
        self.request.user = self.reviewer

    def test_approve_action_records_reviewer_and_time(self):
        self.model_admin.approve_submissions(
            self.request,
            FormSubmission.objects.filter(pk=self.submission.pk),
        )

        self.submission.refresh_from_db()
        self.assertEqual(
            self.submission.review_status,
            FormSubmission.ReviewStatus.APPROVED,
        )
        self.assertEqual(self.submission.reviewed_by, self.reviewer)
        self.assertIsNotNone(self.submission.reviewed_at)

    def test_reject_action_records_reviewer_and_time(self):
        self.model_admin.reject_submissions(
            self.request,
            FormSubmission.objects.filter(pk=self.submission.pk),
        )

        self.submission.refresh_from_db()
        self.assertEqual(
            self.submission.review_status,
            FormSubmission.ReviewStatus.REJECTED,
        )
        self.assertEqual(self.submission.reviewed_by, self.reviewer)
        self.assertIsNotNone(self.submission.reviewed_at)

    def test_pending_action_clears_review_information(self):
        self.model_admin.approve_submissions(
            self.request,
            FormSubmission.objects.filter(pk=self.submission.pk),
        )
        self.model_admin.reset_submissions_to_pending(
            self.request,
            FormSubmission.objects.filter(pk=self.submission.pk),
        )

        self.submission.refresh_from_db()
        self.assertEqual(
            self.submission.review_status,
            FormSubmission.ReviewStatus.PENDING,
        )
        self.assertIsNone(self.submission.reviewed_by)
        self.assertIsNone(self.submission.reviewed_at)
