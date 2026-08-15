from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from accounts.models import User
from forms_builder.models import EventForm, FormAnswer, FormQuestion

from .management.commands.setup_conference_registration import EVENT_CODE


@override_settings(PUBLIC_BASE_URL="https://events.example.test")
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
                f"question_{questions['Full Name'].pk}": "Dr. Amina Mushi",
                f"question_{questions['Institution Name'].pk}": "University of Dodoma",
                f"question_{questions['Position / Title'].pk}": "Lecturer",
                f"question_{questions['Email Address'].pk}": "amina@example.test",
                f"question_{questions['Phone Number'].pk}": "+255700000001",
                f"question_{questions['Which session(s) will you attend?'].pk}": [
                    "BASIC_EDUCATION_17_AUG",
                    "STI_21_AUG",
                ],
            },
        )
        self.assertEqual(response.status_code, 200)
        answer = FormAnswer.objects.get(
            submission__event_form=self.event_form,
            question=questions["Which session(s) will you attend?"],
        )
        self.assertEqual(
            set(answer.selected_options.values_list("value", flat=True)),
            {"BASIC_EDUCATION_17_AUG", "STI_21_AUG"},
        )

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
