from django.test import TestCase

# Create your tests here.
from datetime import datetime, timedelta
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core import mail
from django.core.management import call_command
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
    Booth,
    BoothInterest,
    BoothOffering,
    EventForm,
    EventReminder,
    FormAnswer,
    FormQuestion,
    FormSection,
    FormSubmission,
    NotificationLog,
    Payment,
    QuestionOption,
)
from .notifications import (
    process_due_reminders,
    process_event_reminder,
    resend_notification,
    send_submission_notification,
)

from .services import (
    certificate_number,
    event_date_range,
    generate_qr_png,
    participant_check_in_url,
    public_form_path,
    public_form_url,
    safe_spreadsheet_value,
    sync_badge_identity_from_answers,
)
from .templatetags.form_text import simple_rich_text


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

    def test_certificate_number_is_short_and_stable(self):
        submission = SimpleNamespace(
            participant_token="12345678-1234-5678-1234-567812345678",
            event_form=SimpleNamespace(
                event=SimpleNamespace(
                    starts_at=timezone.now().replace(year=2026),
                )
            ),
        )

        self.assertEqual(certificate_number(submission), "CERT-2026-1234567812")

    def test_same_month_event_date_uses_compact_range(self):
        event = SimpleNamespace(
            starts_at=timezone.make_aware(datetime(2026, 8, 15, 8)),
            ends_at=timezone.make_aware(datetime(2026, 8, 24, 17)),
        )

        self.assertEqual(event_date_range(event, "en"), "15–24 August 2026")
        self.assertEqual(event_date_range(event, "sw"), "15–24 Agosti 2026")

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

    def test_introduction_supports_safe_bold_text(self):
        rendered = str(
            simple_rich_text(
                "Contact **Jane Doe** on **+255 700 000 000**."
            )
        )

        self.assertIn("<strong>Jane Doe</strong>", rendered)
        self.assertIn("<strong>+255 700 000 000</strong>", rendered)

    def test_introduction_escapes_html_from_administrator(self):
        rendered = str(simple_rich_text("<script>alert('x')</script>"))

        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)


class ParticipantPaymentTests(TestCase):
    def setUp(self):
        category = EventCategory.objects.create(
            name_sw="Maonesho", name_en="Exhibition", code="PAY",
        )
        starts_at = timezone.now() + timedelta(days=10)
        self.event = Event.objects.create(
            category=category, code="PAY-2026",
            title_sw="Tukio la Malipo", title_en="Payment Event",
            starts_at=starts_at, ends_at=starts_at + timedelta(days=2),
            payment_enabled=True, participation_fee="50000.00",
            payment_instructions_sw="Lipa kupitia benki.",
            payment_instructions_en="Pay through the bank.",
        )
        event_form = EventForm.objects.create(
            event=self.event, name_sw="Usajili", name_en="Registration",
            is_published=True,
        )
        self.submission = FormSubmission.objects.create(
            event_form=event_form, submitter_email="person@example.org",
        )
        self.url = (
            f"/en/participants/{self.submission.participant_token}/payment/"
        )

    def test_participant_can_submit_payment_information(self):
        response = self.client.post(
            self.url,
            {"method": Payment.Method.BANK, "transaction_reference": "TX-100"},
        )
        self.assertRedirects(response, self.url)
        payment = Payment.objects.get(submission=self.submission)
        self.assertEqual(payment.amount, self.event.participation_fee)
        self.assertEqual(payment.transaction_reference, "TX-100")
        self.assertEqual(payment.status, Payment.Status.PENDING)

    def test_pending_payment_cannot_be_submitted_twice(self):
        Payment.objects.create(
            submission=self.submission, amount=self.event.participation_fee,
            method=Payment.Method.BANK, transaction_reference="TX-OLD",
        )
        response = self.client.post(
            self.url,
            {"method": Payment.Method.BANK, "transaction_reference": "TX-NEW"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.submission.payments.count(), 1)

    def test_payment_page_is_unavailable_when_event_disables_payments(self):
        self.event.payment_enabled = False
        self.event.save(update_fields=["payment_enabled"])
        self.assertEqual(self.client.get(self.url).status_code, 404)


class PublicEvaluationTests(TestCase):
    def setUp(self):
        category = EventCategory.objects.create(
            name_sw="Maonesho",
            name_en="Exhibition",
            code="EVAL",
        )
        starts_at = timezone.now() + timedelta(days=5)
        self.event = Event.objects.create(
            category=category,
            code="VISITOR-2026",
            title_sw="Wiki ya Ubunifu",
            title_en="Innovation Week",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(days=4),
            registration_enabled=False,
            evaluation_enabled=True,
        )
        self.event_form = EventForm.objects.create(
            event=self.event,
            name_sw="Tathmini ya Mgeni",
            name_en="Visitor Evaluation",
            form_type=EventForm.FormType.EVALUATION,
            is_published=True,
            success_message_sw="Asante kwa maoni yako.",
            success_message_en="Thank you for your feedback.",
        )
        section = FormSection.objects.create(
            event_form=self.event_form,
            title_sw="Maoni",
            title_en="Feedback",
        )
        self.question = FormQuestion.objects.create(
            section=section,
            label_sw="Ulipenda nini?",
            label_en="What did you like?",
            question_type=FormQuestion.QuestionType.LONG_TEXT,
            is_required=True,
        )
        self.url = (
            f"/en/events/{self.event.slug}/forms/{self.event_form.slug}/"
        )

    def test_anonymous_visitor_can_submit_evaluation(self):
        page_response = self.client.get(self.url)
        self.assertEqual(page_response.status_code, 200)
        self.assertContains(page_response, "Submit evaluation")

        response = self.client.post(
            self.url,
            {f"question_{self.question.pk}": "The learning booth."},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        submission = FormSubmission.objects.get(event_form=self.event_form)
        self.assertIsNone(submission.submitted_by)
        self.assertEqual(submission.badge_name, "")
        self.assertEqual(
            submission.answers.get(question=self.question).text_value,
            "The learning booth.",
        )

        success_response = self.client.get(payload["redirect_url"])
        self.assertContains(success_response, "Thank you for your feedback")
        self.assertNotContains(success_response, "Check registration status")

    def test_hidden_conditional_section_is_not_required_or_saved(self):
        participation = FormQuestion.objects.create(
            section=self.question.section,
            label_sw="Aina ya ushiriki",
            label_en="Participation type",
            question_type=FormQuestion.QuestionType.MULTIPLE_CHOICE,
            is_required=True,
            display_order=2,
        )
        QuestionOption.objects.create(
            question=participation,
            value="CONFERENCE",
            label_sw="Kongamano",
            label_en="Conference",
        )
        QuestionOption.objects.create(
            question=participation,
            value="EXHIBITION",
            label_sw="Maonesho",
            label_en="Exhibition",
        )
        conference_section = FormSection.objects.create(
            event_form=self.event_form,
            title_sw="Kongamano",
            title_en="Conference",
            display_order=2,
            condition_question=participation,
            condition_value="CONFERENCE",
        )
        conditional_question = FormQuestion.objects.create(
            section=conference_section,
            label_sw="Eneo la kongamano",
            label_en="Conference area",
            is_required=True,
        )

        response = self.client.post(
            self.url,
            {
                f"question_{self.question.pk}": "Exhibition only.",
                f"question_{participation.pk}": "EXHIBITION",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        submission = FormSubmission.objects.get(event_form=self.event_form)
        self.assertFalse(
            submission.answers.filter(question=conditional_question).exists()
        )

    def test_visible_conditional_section_becomes_required(self):
        participation = FormQuestion.objects.create(
            section=self.question.section,
            label_sw="Aina ya ushiriki",
            label_en="Participation type",
            question_type=FormQuestion.QuestionType.MULTIPLE_CHOICE,
            is_required=True,
            display_order=2,
        )
        QuestionOption.objects.create(
            question=participation,
            value="CONFERENCE",
            label_sw="Kongamano",
            label_en="Conference",
        )
        conference_section = FormSection.objects.create(
            event_form=self.event_form,
            title_sw="Kongamano",
            title_en="Conference",
            display_order=2,
            condition_question=participation,
            condition_value="CONFERENCE",
        )
        conditional_question = FormQuestion.objects.create(
            section=conference_section,
            label_sw="Eneo la kongamano",
            label_en="Conference area",
            is_required=True,
        )

        response = self.client.post(
            self.url,
            {
                f"question_{self.question.pk}": "Conference visit.",
                f"question_{participation.pk}": "CONFERENCE",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            str(conditional_question.pk),
            response.json()["errors"],
        )

    def test_representative_contact_is_used_when_institution_comes_first(self):
        institution_email = FormQuestion.objects.create(
            section=self.question.section,
            label_sw="Barua pepe ya taasisi",
            label_en="Institution Email Address",
            question_type=FormQuestion.QuestionType.EMAIL,
            is_required=True,
            display_order=2,
        )
        representative_email = FormQuestion.objects.create(
            section=self.question.section,
            label_sw="Barua pepe ya mwakilishi",
            label_en="Representative Email Address",
            question_type=FormQuestion.QuestionType.EMAIL,
            is_required=True,
            display_order=3,
        )

        response = self.client.post(
            self.url,
            {
                f"question_{self.question.pk}": "Useful event.",
                f"question_{institution_email.pk}": "office@example.org",
                f"question_{representative_email.pk}": "person@example.org",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        submission = FormSubmission.objects.get(event_form=self.event_form)
        self.assertEqual(submission.submitter_email, "person@example.org")

    def test_disabled_evaluation_is_not_public(self):
        self.event.evaluation_enabled = False
        self.event.save(update_fields=["evaluation_enabled"])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)

    def test_anonymous_browser_cannot_submit_duplicate_evaluation(self):
        answer = {f"question_{self.question.pk}": "Excellent exhibits."}

        first_response = self.client.post(
            self.url,
            answer,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        second_response = self.client.post(
            self.url,
            answer,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 409)
        self.assertTrue(second_response.json()["duplicate"])
        self.assertEqual(
            FormSubmission.objects.filter(event_form=self.event_form).count(),
            1,
        )

    def test_repeat_evaluations_can_be_enabled_for_shared_devices(self):
        self.event_form.allow_multiple_submissions = True
        self.event_form.save(update_fields=["allow_multiple_submissions"])
        answer = {f"question_{self.question.pk}": "Useful technology."}

        self.client.post(
            self.url,
            answer,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        second_response = self.client.post(
            self.url,
            answer,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(
            FormSubmission.objects.filter(event_form=self.event_form).count(),
            2,
        )

    def test_report_officer_can_view_ratings_and_download_csv(self):
        rating_question = FormQuestion.objects.create(
            section=self.question.section,
            label_sw="Tathmini ya jumla",
            label_en="Overall rating",
            question_type=FormQuestion.QuestionType.DROPDOWN,
            is_required=True,
            display_order=2,
        )
        rating_five = QuestionOption.objects.create(
            question=rating_question,
            value="5",
            label_sw="Bora sana",
            label_en="Excellent",
            display_order=1,
        )
        rating_three = QuestionOption.objects.create(
            question=rating_question,
            value="3",
            label_sw="Nzuri",
            label_en="Good",
            display_order=2,
        )
        for index, option in enumerate((rating_five, rating_three), start=1):
            submission = FormSubmission.objects.create(
                event_form=self.event_form,
                language="en",
            )
            FormAnswer.objects.create(
                submission=submission,
                question=self.question,
                text_value=f"Feedback {index}",
            )
            rating_answer = FormAnswer.objects.create(
                submission=submission,
                question=rating_question,
            )
            rating_answer.selected_options.set([option])

        report_officer = get_user_model().objects.create_user(
            username="evaluation-reporter",
            email="evaluation-reporter@example.org",
            password="test-password",
            role="REPORT_OFFICER",
            is_staff=True,
        )
        self.client.force_login(report_officer)

        response = self.client.get(
            "/en/reports/evaluations/",
            {"form": self.event_form.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Total responses")
        self.assertContains(response, "Overall rating")
        self.assertContains(response, "4.00/5")
        self.assertContains(response, "Feedback 1")

        csv_response = self.client.get(
            "/en/reports/evaluations/export/",
            {"form": self.event_form.pk},
        )
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn("text/csv", csv_response["Content-Type"])
        csv_content = csv_response.content.decode("utf-8-sig")
        self.assertIn("Overall rating", csv_content)
        self.assertIn("Excellent", csv_content)
        self.assertIn("Good", csv_content)

    def test_participant_cannot_access_evaluation_reports(self):
        participant = get_user_model().objects.create_user(
            username="evaluation-participant",
            email="evaluation-participant@example.org",
            password="test-password",
            role="PARTICIPANT",
        )
        self.client.force_login(participant)

        response = self.client.get("/en/reports/evaluations/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])


class BoothManagementTests(TestCase):
    def setUp(self):
        category = EventCategory.objects.create(
            name_sw="Maonesho",
            name_en="Exhibition",
            code="BOOTH",
        )
        starts_at = timezone.now() + timedelta(days=10)
        self.event = Event.objects.create(
            category=category,
            code="BOOTH-2026",
            title_sw="Maonesho ya Teknolojia",
            title_en="Technology Exhibition",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(days=2),
            booth_enabled=True,
        )
        self.event_form = EventForm.objects.create(
            event=self.event,
            name_sw="Usajili wa Waoneshaji",
            name_en="Exhibitor Registration",
            form_type=EventForm.FormType.EXHIBITOR,
            is_published=True,
        )
        self.submission = FormSubmission.objects.create(
            event_form=self.event_form,
            review_status=FormSubmission.ReviewStatus.APPROVED,
            badge_name="Amina Ubunifu",
            badge_organization="Innovation Tanzania",
        )

    def test_approved_exhibitor_can_be_assigned_to_booth(self):
        booth = Booth.objects.create(
            event=self.event,
            code=" a-01 ",
            name_sw="Banda la Ubunifu",
            name_en="Innovation Booth",
            zone_sw="Ukumbi Mkuu",
            zone_en="Main Hall",
            assigned_submission=self.submission,
        )

        self.assertEqual(booth.code, "A-01")
        self.assertEqual(booth.status, Booth.Status.ASSIGNED)
        self.assertEqual(self.submission.booth_assignment, booth)

    def test_pending_exhibitor_cannot_be_assigned(self):
        self.submission.review_status = FormSubmission.ReviewStatus.PENDING
        self.submission.save(update_fields=["review_status"])

        with self.assertRaises(ValidationError):
            Booth.objects.create(
                event=self.event,
                code="A-02",
                name_sw="Banda la Pili",
                name_en="Second Booth",
                assigned_submission=self.submission,
            )

    def test_exhibitor_cannot_be_assigned_to_two_booths(self):
        Booth.objects.create(
            event=self.event,
            code="A-03",
            name_sw="Banda la Tatu",
            name_en="Third Booth",
            assigned_submission=self.submission,
        )

        with self.assertRaises(ValidationError):
            Booth.objects.create(
                event=self.event,
                code="A-04",
                name_sw="Banda la Nne",
                name_en="Fourth Booth",
                assigned_submission=self.submission,
            )

    def test_cross_event_assignment_is_rejected(self):
        second_event = Event.objects.create(
            category=self.event.category,
            code="OTHER-2026",
            title_sw="Tukio Jingine",
            title_en="Other Event",
            starts_at=self.event.starts_at,
            ends_at=self.event.ends_at,
            booth_enabled=True,
        )

        with self.assertRaises(ValidationError):
            Booth.objects.create(
                event=second_event,
                code="B-01",
                name_sw="Banda la Tukio Jingine",
                name_en="Other Event Booth",
                assigned_submission=self.submission,
            )

    def test_public_directory_detail_and_qr_are_available(self):
        booth = Booth.objects.create(
            event=self.event,
            code="T-01",
            name_sw="Banda la Teknolojia",
            name_en="Technology Booth",
            zone_sw="Ukumbi Mkuu",
            zone_en="Main Hall",
            assigned_submission=self.submission,
            status=Booth.Status.READY,
        )

        directory_response = self.client.get(
            f"/en/events/{self.event.slug}/booths/"
        )
        self.assertEqual(directory_response.status_code, 200)
        self.assertContains(directory_response, "Technology Booth")
        self.assertContains(directory_response, "Innovation Tanzania")

        detail_response = self.client.get(
            f"/en/booths/{booth.public_token}/"
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "T-01")
        self.assertContains(detail_response, "Amina Ubunifu")
        self.assertContains(detail_response, "Main Hall")

        qr_response = self.client.get(
            f"/en/booths/{booth.public_token}/qr/"
        )
        self.assertEqual(qr_response.status_code, 200)
        self.assertEqual(qr_response["Content-Type"], "image/png")
        self.assertTrue(qr_response.content.startswith(b"\x89PNG"))

    def test_unassigned_or_closed_booth_is_not_public(self):
        booth = Booth.objects.create(
            event=self.event,
            code="T-02",
            name_sw="Banda Lililofungwa",
            name_en="Closed Booth",
            assigned_submission=self.submission,
            status=Booth.Status.CLOSED,
        )

        directory_response = self.client.get(
            f"/en/events/{self.event.slug}/booths/"
        )
        self.assertNotContains(directory_response, "Closed Booth")
        detail_response = self.client.get(
            f"/en/booths/{booth.public_token}/"
        )
        self.assertEqual(detail_response.status_code, 404)

    def test_booth_offerings_contacts_and_visitor_interest(self):
        booth = Booth.objects.create(
            event=self.event,
            code="T-03",
            name_sw="Banda la Kilimo",
            name_en="Agriculture Booth",
            zone_sw="Eneo la Nje",
            zone_en="Outdoor Zone",
            assigned_submission=self.submission,
            status=Booth.Status.READY,
            description_sw="Teknolojia za kisasa za kilimo.",
            description_en="Modern agricultural technologies.",
            public_email="booth@example.org",
            public_phone="+255700000001",
            public_website="https://example.org",
        )
        offering = BoothOffering.objects.create(
            booth=booth,
            offering_type=BoothOffering.OfferingType.TECHNOLOGY,
            name_sw="Umwagiliaji Mahiri",
            name_en="Smart Irrigation",
            description_sw="Mfumo wa kuokoa maji.",
            description_en="A water-saving system.",
        )
        url = f"/en/booths/{booth.public_token}/"

        page_response = self.client.get(url)
        self.assertEqual(page_response.status_code, 200)
        self.assertContains(page_response, "Smart Irrigation")
        self.assertContains(page_response, "Call exhibitor")
        self.assertContains(page_response, "Visit website")

        missing_contact_response = self.client.post(
            url,
            {"visitor_name": "Interested Visitor"},
        )
        self.assertEqual(missing_contact_response.status_code, 200)
        self.assertContains(
            missing_contact_response,
            "Enter an email address or phone number.",
        )
        self.assertFalse(BoothInterest.objects.exists())

        response = self.client.post(
            url,
            {
                "visitor_name": "Interested Visitor",
                "email": "visitor@example.org",
                "phone": "",
                "offering": str(offering.pk),
                "message": "Please contact me about pricing.",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("?interest=success", response["Location"])
        interest = BoothInterest.objects.get()
        self.assertEqual(interest.booth, booth)
        self.assertEqual(interest.offering, offering)
        self.assertEqual(interest.email, "visitor@example.org")

        success_response = self.client.get(response["Location"])
        self.assertContains(
            success_response,
            "Your interest has been sent to the exhibitor.",
        )

    def test_interest_cannot_select_offering_from_another_booth(self):
        first_booth = Booth.objects.create(
            event=self.event,
            code="T-04",
            name_sw="Banda la Kwanza",
            name_en="First Booth",
            assigned_submission=self.submission,
        )
        second_submission = FormSubmission.objects.create(
            event_form=self.event_form,
            review_status=FormSubmission.ReviewStatus.APPROVED,
            badge_name="Second Exhibitor",
        )
        second_booth = Booth.objects.create(
            event=self.event,
            code="T-05",
            name_sw="Banda la Pili",
            name_en="Second Booth",
            assigned_submission=second_submission,
        )
        other_offering = BoothOffering.objects.create(
            booth=second_booth,
            name_sw="Bidhaa Nyingine",
            name_en="Other Product",
        )

        with self.assertRaises(ValidationError):
            BoothInterest.objects.create(
                booth=first_booth,
                offering=other_offering,
                email="visitor@example.org",
            )


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PUBLIC_BASE_URL="https://events.example.org",
)
class SubmissionNotificationTests(TestCase):
    def setUp(self):
        category = EventCategory.objects.create(
            name_sw="Mkutano",
            name_en="Conference",
            code="MAIL",
        )
        starts_at = timezone.now() + timedelta(days=20)
        event = Event.objects.create(
            category=category,
            code="MAIL-2026",
            title_sw="Tukio la Mawasiliano",
            title_en="Communication Event",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(days=1),
            badge_enabled=True,
        )
        event_form = EventForm.objects.create(
            event=event,
            name_sw="Usajili",
            name_en="Registration",
            is_published=True,
        )
        self.submission = FormSubmission.objects.create(
            event_form=event_form,
            submitter_email="participant@example.org",
            language="en",
        )

    def test_registration_received_email_is_sent_and_logged(self):
        log = send_submission_notification(
            self.submission,
            NotificationLog.NotificationType.REGISTRATION_RECEIVED,
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Registration received", mail.outbox[0].subject)
        self.assertIn(self.submission.reference_number, mail.outbox[0].body)
        self.assertIn("https://events.example.org", mail.outbox[0].body)
        self.assertEqual(log.delivery_status, NotificationLog.DeliveryStatus.SENT)
        self.assertIsNotNone(log.sent_at)

    def test_public_registration_automatically_sends_receipt(self):
        section = FormSection.objects.create(
            event_form=self.submission.event_form,
            title_sw="Mawasiliano",
            title_en="Contact",
        )
        email_question = FormQuestion.objects.create(
            section=section,
            label_sw="Baruapepe",
            label_en="Email",
            question_type=FormQuestion.QuestionType.EMAIL,
            is_required=True,
        )
        event = self.submission.event_form.event
        url = (
            f"/en/events/{event.slug}/forms/"
            f"{self.submission.event_form.slug}/"
        )

        response = self.client.post(
            url,
            {f"question_{email_question.pk}": "new@example.org"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        created_submission = FormSubmission.objects.get(
            submitter_email="new@example.org"
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(
            NotificationLog.objects.filter(
                submission=created_submission,
                notification_type=(
                    NotificationLog.NotificationType.REGISTRATION_RECEIVED
                ),
                delivery_status=NotificationLog.DeliveryStatus.SENT,
            ).exists()
        )

    def test_missing_email_is_logged_as_skipped(self):
        self.submission.submitter_email = ""
        self.submission.save(update_fields=["submitter_email"])

        log = send_submission_notification(
            self.submission,
            NotificationLog.NotificationType.REGISTRATION_APPROVED,
        )

        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(
            log.delivery_status,
            NotificationLog.DeliveryStatus.SKIPPED,
        )
        self.assertTrue(log.error_message)

    def test_kiswahili_notification_uses_kiswahili_content(self):
        self.submission.language = "sw"
        self.submission.save(update_fields=["language"])

        send_submission_notification(
            self.submission,
            NotificationLog.NotificationType.REGISTRATION_APPROVED,
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Usajili umeidhinishwa", mail.outbox[0].subject)
        self.assertIn("Namba ya kumbukumbu", mail.outbox[0].body)

    def test_email_backend_failure_is_logged_without_raising(self):
        with patch(
            "forms_builder.notifications.send_mail",
            side_effect=RuntimeError("SMTP unavailable"),
        ):
            log = send_submission_notification(
                self.submission,
                NotificationLog.NotificationType.REGISTRATION_REJECTED,
            )

        self.assertEqual(
            log.delivery_status,
            NotificationLog.DeliveryStatus.FAILED,
        )
        self.assertIn("SMTP unavailable", log.error_message)

    def test_reminder_sends_only_to_approved_participants(self):
        self.submission.review_status = FormSubmission.ReviewStatus.APPROVED
        self.submission.save(update_fields=["review_status"])
        missing_email = FormSubmission.objects.create(
            event_form=self.submission.event_form,
            review_status=FormSubmission.ReviewStatus.APPROVED,
            language="sw",
        )
        FormSubmission.objects.create(
            event_form=self.submission.event_form,
            submitter_email="pending@example.org",
            review_status=FormSubmission.ReviewStatus.PENDING,
        )
        reminder = EventReminder.objects.create(
            event=self.submission.event_form.event,
            subject_sw="Kumbusho la tukio",
            subject_en="Event reminder",
            message_sw="Tafadhali fika kwa wakati.",
            message_en="Please arrive on time.",
            scheduled_for=timezone.now(),
            status=EventReminder.Status.SCHEDULED,
        )

        processed = process_event_reminder(reminder)

        self.assertEqual(processed.status, EventReminder.Status.COMPLETED)
        self.assertEqual(processed.sent_count, 1)
        self.assertEqual(processed.skipped_count, 1)
        self.assertEqual(processed.failed_count, 0)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Please arrive on time.", mail.outbox[0].body)
        self.assertEqual(
            NotificationLog.objects.filter(event_reminder=reminder).count(),
            2,
        )
        self.assertFalse(
            NotificationLog.objects.filter(
                event_reminder=reminder,
                submission__submitter_email="pending@example.org",
            ).exists()
        )
        self.assertTrue(
            NotificationLog.objects.filter(
                event_reminder=reminder,
                submission=missing_email,
                delivery_status=NotificationLog.DeliveryStatus.SKIPPED,
            ).exists()
        )

        process_event_reminder(reminder)
        self.assertEqual(len(mail.outbox), 1)

    def test_due_reminder_management_command(self):
        self.submission.review_status = FormSubmission.ReviewStatus.APPROVED
        self.submission.save(update_fields=["review_status"])
        due = EventReminder.objects.create(
            event=self.submission.event_form.event,
            subject_sw="Kumbusho",
            subject_en="Reminder",
            message_sw="Tukio ni leo.",
            message_en="The event is today.",
            scheduled_for=timezone.now() - timedelta(minutes=1),
            status=EventReminder.Status.SCHEDULED,
        )
        future = EventReminder.objects.create(
            event=self.submission.event_form.event,
            subject_sw="Kumbusho la baadaye",
            subject_en="Future reminder",
            message_sw="Ujumbe wa baadaye.",
            message_en="A future message.",
            scheduled_for=timezone.now() + timedelta(days=1),
            status=EventReminder.Status.SCHEDULED,
        )
        output = StringIO()

        call_command("send_due_reminders", stdout=output)

        due.refresh_from_db()
        future.refresh_from_db()
        self.assertEqual(due.status, EventReminder.Status.COMPLETED)
        self.assertEqual(future.status, EventReminder.Status.SCHEDULED)
        self.assertIn("Processed 1 due reminder", output.getvalue())

    @override_settings(REMINDER_SCHEDULER_TOKEN="scheduler-secret")
    def test_secure_scheduler_endpoint_processes_due_reminders_once(self):
        self.submission.review_status = FormSubmission.ReviewStatus.APPROVED
        self.submission.save(update_fields=["review_status"])
        reminder = EventReminder.objects.create(
            event=self.submission.event_form.event,
            subject_sw="Kumbusho",
            subject_en="Reminder",
            message_sw="Tukio ni leo.",
            message_en="The event is today.",
            scheduled_for=timezone.now() - timedelta(minutes=1),
            status=EventReminder.Status.SCHEDULED,
        )

        forbidden = self.client.post(
            "/automation/reminders/run/",
            HTTP_AUTHORIZATION="Bearer incorrect",
        )
        first = self.client.post(
            "/automation/reminders/run/",
            HTTP_X_REMINDER_TOKEN="scheduler-secret",
        )
        second = self.client.post(
            "/automation/reminders/run/",
            HTTP_AUTHORIZATION="Bearer scheduler-secret",
        )

        reminder.refresh_from_db()
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), {"processed": 1})
        self.assertEqual(second.json(), {"processed": 0})
        self.assertEqual(reminder.status, EventReminder.Status.COMPLETED)
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(REMINDER_SCHEDULER_TOKEN="")
    def test_scheduler_endpoint_requires_server_configuration(self):
        response = self.client.post("/automation/reminders/run/")

        self.assertEqual(response.status_code, 503)

    def test_notification_can_be_resent(self):
        original_log = send_submission_notification(
            self.submission,
            NotificationLog.NotificationType.REGISTRATION_RECEIVED,
        )

        resent_log = resend_notification(original_log)

        self.assertEqual(len(mail.outbox), 2)
        self.assertNotEqual(original_log.pk, resent_log.pk)
        self.assertEqual(
            resent_log.delivery_status,
            NotificationLog.DeliveryStatus.SENT,
        )


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
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
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(
            "approved" in mail.outbox[0].subject.lower()
            or "umeidhinishwa" in mail.outbox[0].subject.lower()
        )
        self.assertTrue(
            NotificationLog.objects.filter(
                submission=self.submission,
                notification_type=(
                    NotificationLog.NotificationType.REGISTRATION_APPROVED
                ),
                delivery_status=NotificationLog.DeliveryStatus.SENT,
            ).exists()
        )

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
        expected_certificate_number = certificate_number(self.submission)
        self.assertContains(response, expected_certificate_number)
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
        self.assertContains(
            verification_response,
            expected_certificate_number,
        )

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
