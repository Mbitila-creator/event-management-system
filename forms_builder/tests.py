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
from checkin.models import ParticipantCheckIn

from .admin import FormSubmissionAdmin
from .models import (
    EventForm,
    FormAnswer,
    FormQuestion,
    FormSection,
    FormSubmission,
)

from .services import (
    generate_qr_png,
    participant_check_in_url,
    public_form_path,
    public_form_url,
    safe_spreadsheet_value,
    sync_badge_identity_from_answers,
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

    @override_settings(PUBLIC_BASE_URL="https://events.example.org")
    def test_participant_qr_targets_automatic_check_in(self):
        submission = SimpleNamespace(
            participant_token="12345678-1234-5678-1234-567812345678"
        )

        url = participant_check_in_url(
            submission,
            language="en",
        )

        self.assertEqual(
            url,
            (
                "https://events.example.org/en/check-in/"
                "12345678-1234-5678-1234-567812345678/?auto=1"
            ),
        )

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

    def test_status_lookup_accepts_matching_email(self):
        FormSubmission.objects.filter(pk=self.submission.pk).update(
            review_status=FormSubmission.ReviewStatus.APPROVED,
            reviewed_by=self.reviewer,
            reviewed_at=timezone.now(),
            review_notes="Private internal decision notes",
        )

        response = self.client.post(
            "/en/registration-status/",
            {
                "reference_number": self.submission.reference_number,
                "contact": "PARTICIPANT@example.org",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Registration approved")
        self.assertNotContains(response, "Private internal decision notes")

    def test_kiswahili_status_uses_translated_choice_label(self):
        FormSubmission.objects.filter(pk=self.submission.pk).update(
            review_status=FormSubmission.ReviewStatus.APPROVED,
            reviewed_by=self.reviewer,
            reviewed_at=timezone.now(),
        )

        response = self.client.post(
            "/sw/registration-status/",
            {
                "reference_number": self.submission.reference_number,
                "contact": "participant@example.org",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Imepitishwa")
        self.assertContains(response, "Usajili umeidhinishwa")
        self.assertNotContains(response, ">Approved<")

    def test_status_lookup_rejects_incorrect_contact(self):
        response = self.client.post(
            "/en/registration-status/",
            {
                "reference_number": self.submission.reference_number,
                "contact": "someone-else@example.org",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "We could not verify a registration with those details.",
        )
        self.assertNotContains(response, self.submission.event_form.name_en)

    def test_status_page_prefills_reference_from_success_link(self):
        response = self.client.get(
            "/en/registration-status/",
            {"reference": self.submission.reference_number},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.submission.reference_number)

    def test_pending_submission_cannot_open_badge(self):
        response = self.client.get(
            f"/en/participants/{self.submission.participant_token}/badge/"
        )

        self.assertEqual(response.status_code, 404)

    def test_approved_submission_can_open_printable_badge(self):
        FormSubmission.objects.filter(pk=self.submission.pk).update(
            review_status=FormSubmission.ReviewStatus.APPROVED,
            reviewed_by=self.reviewer,
            reviewed_at=timezone.now(),
            badge_name="Asha Mwangaza",
            badge_organization="Innovation Institute",
            badge_title="Exhibitor",
        )

        response = self.client.get(
            f"/en/participants/{self.submission.participant_token}/badge/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Asha Mwangaza")
        self.assertContains(response, "Innovation Institute")
        self.assertContains(response, "Exhibitor")
        self.assertContains(response, self.submission.reference_number)

    def test_approved_participant_qr_is_png(self):
        FormSubmission.objects.filter(pk=self.submission.pk).update(
            review_status=FormSubmission.ReviewStatus.APPROVED,
            reviewed_by=self.reviewer,
            reviewed_at=timezone.now(),
        )

        response = self.client.get(
            (
                f"/en/participants/{self.submission.participant_token}"
                "/badge/qr/"
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertTrue(response.content.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_checked_in_participant_can_open_certificate(self):
        event = self.submission.event_form.event
        event.certificate_enabled = True
        event.save(update_fields=["certificate_enabled"])
        FormSubmission.objects.filter(pk=self.submission.pk).update(
            review_status=FormSubmission.ReviewStatus.APPROVED,
            reviewed_by=self.reviewer,
            reviewed_at=timezone.now(),
            badge_name="Asha Mwangaza",
            badge_organization="Innovation Institute",
        )
        ParticipantCheckIn.objects.create(
            submission=self.submission,
            checked_in_by=self.reviewer,
        )

        response = self.client.get(
            f"/en/participants/{self.submission.participant_token}/certificate/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Certificate of Participation")
        self.assertContains(response, "Asha Mwangaza")
        self.assertContains(response, "Innovation Institute")
        self.assertContains(response, f"CERT-{event.code}-")
        self.assertContains(response, "Download PDF certificate")
        self.assertContains(response, "Certificate verification QR code")

        pdf_response = self.client.get(
            f"/en/participants/{self.submission.participant_token}/certificate/pdf/"
        )
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")
        self.assertTrue(pdf_response.content.startswith(b"%PDF"))
        self.assertIn("attachment;", pdf_response["Content-Disposition"])

        qr_response = self.client.get(
            f"/en/participants/{self.submission.participant_token}/certificate/qr/"
        )
        self.assertEqual(qr_response.status_code, 200)
        self.assertEqual(qr_response["Content-Type"], "image/png")
        self.assertTrue(qr_response.content.startswith(b"\x89PNG"))

        verification_response = self.client.get(
            f"/en/certificates/verify/{self.submission.participant_token}/"
        )
        self.assertEqual(verification_response.status_code, 200)
        self.assertContains(verification_response, "Certificate verified")
        self.assertContains(verification_response, "Asha Mwangaza")
        self.assertContains(verification_response, f"CERT-{event.code}-")

    def test_certificate_requires_participant_check_in(self):
        event = self.submission.event_form.event
        event.certificate_enabled = True
        event.save(update_fields=["certificate_enabled"])
        FormSubmission.objects.filter(pk=self.submission.pk).update(
            review_status=FormSubmission.ReviewStatus.APPROVED,
        )

        response = self.client.get(
            f"/en/participants/{self.submission.participant_token}/certificate/"
        )

        self.assertEqual(response.status_code, 404)

    def test_certificate_requires_event_setting(self):
        FormSubmission.objects.filter(pk=self.submission.pk).update(
            review_status=FormSubmission.ReviewStatus.APPROVED,
        )
        ParticipantCheckIn.objects.create(
            submission=self.submission,
            checked_in_by=self.reviewer,
        )

        response = self.client.get(
            f"/en/participants/{self.submission.participant_token}/certificate/"
        )

        self.assertEqual(response.status_code, 404)

    def test_badge_identity_is_filled_from_registration_answers(self):
        section = FormSection.objects.create(
            event_form=self.submission.event_form,
            title_sw="Taarifa za Mwakilishi",
            title_en="Representative Information",
        )
        name_question = FormQuestion.objects.create(
            section=section,
            label_sw="Jina la Mwakilishi",
            label_en="Representative Name",
        )
        organization_question = FormQuestion.objects.create(
            section=section,
            label_sw="Jina la Taasisi",
            label_en="Institution Name",
        )
        FormAnswer.objects.create(
            submission=self.submission,
            question=name_question,
            text_value="Amina Ubunifu",
        )
        FormAnswer.objects.create(
            submission=self.submission,
            question=organization_question,
            text_value="Taasisi ya Elimu",
        )

        sync_badge_identity_from_answers(self.submission)
        self.submission.refresh_from_db()

        self.assertEqual(self.submission.badge_name, "Amina Ubunifu")
        self.assertEqual(
            self.submission.badge_organization,
            "Taasisi ya Elimu",
        )
        self.assertEqual(self.submission.badge_title, "Mwakilishi")
