from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from accounts.models import User
from forms_builder.models import EventForm, FormAnswer, FormQuestion, FormSubmission

from .management.commands.setup_conference_registration import EVENT_CODE
from .models import ConferenceSession, ConferenceSessionAttendance


@override_settings(
    PUBLIC_BASE_URL="https://events.example.test",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class ConferenceRegistrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_conference_registration", verbosity=0)
        cls.event_form = EventForm.objects.select_related("event").get(
            event__code=EVENT_CODE,
            slug="national-forum-registration",
        )
        cls.admin_user = User.objects.create_user(
            username="conference-admin",
            email="conference-admin@example.test",
            password="safe-test-password",
            role=User.Role.EVENT_ADMIN,
        )
        cls.participant_user = User.objects.create_user(
            username="participant",
            email="participant@example.test",
            password="safe-test-password",
            role=User.Role.PARTICIPANT,
        )

    def submit_registration(self, selected_values=None, name="Dr. Amina Mushi"):
        selected_values = selected_values or [
            "BASIC_EDUCATION_17_AUG",
            "STI_21_AUG",
        ]
        questions = {
            question.label_en: question
            for question in FormQuestion.objects.filter(
                section__event_form=self.event_form,
                is_active=True,
            )
        }
        response = self.client.post(
            reverse(
                "forms_builder:public_event_form",
                kwargs={
                    "event_slug": self.event_form.event.slug,
                    "form_slug": self.event_form.slug,
                },
            ),
            {
                f"question_{questions['Full Name'].pk}": name,
                f"question_{questions['Institution Name'].pk}": "University of Dodoma",
                f"question_{questions['Position / Title'].pk}": "Lecturer",
                f"question_{questions['Email Address'].pk}": "amina@example.test",
                f"question_{questions['Phone Number'].pk}": "+255700000001",
                f"question_{questions['Which session(s) will you attend?'].pk}": selected_values,
            },
        )
        self.assertEqual(response.status_code, 200)
        return FormSubmission.objects.get(
            event_form=self.event_form,
            badge_name=name,
        )

    def test_setup_command_is_idempotent_and_creates_four_session_options(self):
        call_command("setup_conference_registration", verbosity=0)
        self.assertEqual(
            EventForm.objects.filter(event__code=EVENT_CODE).count(),
            1,
        )
        question = FormQuestion.objects.get(
            section__event_form=self.event_form,
            label_en="Which session(s) will you attend?",
        )
        self.assertEqual(question.question_type, "MULTIPLE_CHOICE")
        self.assertEqual(question.options.filter(is_active=True).count(), 4)
        self.assertEqual(
            ConferenceSession.objects.filter(event=self.event_form.event).count(),
            4,
        )

    def test_public_form_shows_invitation_and_session_examples(self):
        response = self.client.get(
            reverse(
                "forms_builder:public_event_form",
                kwargs={
                    "event_slug": self.event_form.event.slug,
                    "form_slug": self.event_form.slug,
                },
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "National Development Vision 2050")
        self.assertContains(response, "Basic Education Session")
        self.assertContains(response, "Higher Education and TVET Session")
        self.assertContains(response, "Fursa Women and Youth Innovation Clinic")

    def test_registration_accepts_more_than_one_session(self):
        submission = self.submit_registration()
        questions = {
            question.label_en: question
            for question in FormQuestion.objects.filter(
                section__event_form=self.event_form,
            )
        }
        answer = FormAnswer.objects.get(
            submission=submission,
            question=questions["Which session(s) will you attend?"],
        )
        self.assertEqual(
            set(answer.selected_options.values_list("value", flat=True)),
            {"BASIC_EDUCATION_17_AUG", "STI_21_AUG"},
        )
        submission.refresh_from_db()
        self.assertEqual(submission.badge_name, "Dr. Amina Mushi")
        self.assertEqual(submission.badge_organization, "University of Dodoma")
        self.assertEqual(submission.badge_title, "Lecturer")

    def test_conference_badge_never_displays_representative_role(self):
        submission = self.submit_registration()
        submission.badge_title = "Representative"
        submission.review_status = FormSubmission.ReviewStatus.APPROVED
        submission.save(update_fields=("badge_title", "review_status", "updated_at"))
        call_command("setup_conference_registration", verbosity=0)
        submission.refresh_from_db()
        self.assertEqual(submission.badge_title, "Lecturer")
        response = self.client.get(
            reverse(
                "forms_builder:participant_badge",
                kwargs={"participant_token": submission.participant_token},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dr. Amina Mushi")
        self.assertContains(response, "University of Dodoma")
        self.assertContains(response, "Institution")
        self.assertContains(response, "Lecturer")
        self.assertNotContains(response, "Representative")

    def test_manager_can_approve_registration_from_conference_dashboard(self):
        submission = self.submit_registration()
        self.client.force_login(self.admin_user)
        with translation.override("sw"):
            url = reverse(
                "conferences:registration_decision",
                kwargs={
                    "form_id": self.event_form.pk,
                    "submission_id": submission.pk,
                    "decision": "approve",
                },
            )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(
            submission.review_status,
            FormSubmission.ReviewStatus.APPROVED,
        )
        self.assertEqual(submission.reviewed_by, self.admin_user)

    def test_selected_participant_can_be_checked_into_each_session_once(self):
        submission = self.submit_registration()
        submission.review_status = FormSubmission.ReviewStatus.APPROVED
        submission.save(update_fields=("review_status", "updated_at"))
        session = ConferenceSession.objects.get(
            event=self.event_form.event,
            registration_option_value="BASIC_EDUCATION_17_AUG",
        )
        self.client.force_login(self.admin_user)
        with translation.override("sw"):
            url = reverse(
                "conferences:session_register",
                kwargs={
                    "form_id": self.event_form.pk,
                    "session_id": session.pk,
                },
            )
        qr_value = (
            "https://events.example.test/sw/check-in/"
            f"{submission.participant_token}/?auto=1"
        )
        first = self.client.post(url, {"identifier": qr_value})
        second = self.client.post(url, {"identifier": qr_value})
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        attendance = ConferenceSessionAttendance.objects.get(
            session=session,
            submission=submission,
        )
        self.assertEqual(attendance.method, ConferenceSessionAttendance.Method.QR)
        self.assertEqual(
            ConferenceSessionAttendance.objects.filter(
                session=session,
                submission=submission,
            ).count(),
            1,
        )
        with translation.override("sw"):
            export_url = reverse(
                "conferences:session_register_csv",
                kwargs={
                    "form_id": self.event_form.pk,
                    "session_id": session.pk,
                },
            )
        export = self.client.get(export_url)
        self.assertEqual(export.status_code, 200)
        self.assertContains(export, "Dr. Amina Mushi")
        self.assertIn("attachment", export["Content-Disposition"])

    def test_participant_cannot_check_in_to_an_unselected_session(self):
        submission = self.submit_registration(
            selected_values=["BASIC_EDUCATION_17_AUG"],
        )
        submission.review_status = FormSubmission.ReviewStatus.APPROVED
        submission.save(update_fields=("review_status", "updated_at"))
        session = ConferenceSession.objects.get(
            event=self.event_form.event,
            registration_option_value="FURSA_CLINIC_22_AUG",
        )
        self.client.force_login(self.admin_user)
        with translation.override("sw"):
            url = reverse(
                "conferences:session_register",
                kwargs={
                    "form_id": self.event_form.pk,
                    "session_id": session.pk,
                },
            )
        response = self.client.post(
            url,
            {"identifier": submission.reference_number},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "did not select this session")
        self.assertFalse(ConferenceSessionAttendance.objects.exists())

    def test_conference_dashboard_shows_session_and_participant_counts(self):
        submission = self.submit_registration()
        submission.review_status = FormSubmission.ReviewStatus.APPROVED
        submission.save(update_fields=("review_status", "updated_at"))
        self.client.force_login(self.admin_user)
        with translation.override("sw"):
            url = reverse(
                "conferences:conference_detail",
                kwargs={"form_id": self.event_form.pk},
            )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Basic Education Session")
        self.assertContains(response, "Dr. Amina Mushi")
        self.assertContains(response, "Badge / QR")

    def test_authorized_staff_can_download_registration_qr(self):
        self.client.force_login(self.admin_user)
        with translation.override("sw"):
            url = reverse(
                "conferences:registration_qr",
                kwargs={"form_id": self.event_form.pk},
            )
        response = self.client.get(url + "?download=1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertTrue(response.content.startswith(b"\x89PNG"))
        self.assertIn("attachment", response["Content-Disposition"])

    def test_participant_cannot_open_staff_conference_centre(self):
        self.client.force_login(self.participant_user)
        with translation.override("sw"):
            url = reverse("conferences:conference_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)
