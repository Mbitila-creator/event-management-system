from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from accounts.models import User
from forms_builder.models import EventForm, FormAnswer, FormQuestion, FormSubmission

from .management.commands.setup_conference_registration import EVENT_CODE
from .models import (
    ConferenceCallForPapers,
    ConferencePaper,
    ConferencePaperReview,
    ConferencePaperReviewAssignment,
    ConferenceProgrammeContributor,
    ConferenceProgrammeItem,
    ConferenceSession,
    ConferenceSessionAttendance,
    ConferenceSpeaker,
    ConferenceReviewer,
    ConferencePresentation,
)


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
        self.assertEqual(
            ConferenceProgrammeItem.objects.filter(
                session__event=self.event_form.event,
            ).count(),
            20,
        )
        self.assertEqual(
            ConferenceCallForPapers.objects.filter(event=self.event_form.event).count(),
            1,
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
        self.assertContains(
            response,
            "images/ministry-of-education-logo.png",
        )
        self.assertContains(
            response,
            'alt="Ministry of Education, Science and Technology logo"',
        )
        self.assertContains(response, "National Development Vision 2050")
        self.assertContains(response, "Basic Education Session")
        self.assertContains(response, "Higher Education and TVET Session")
        self.assertContains(response, "Fursa Women and Youth Innovation Clinic")
        self.assertContains(response, "View conference programme")

    def test_public_programme_shows_published_agenda_and_contributors(self):
        programme_item = ConferenceProgrammeItem.objects.get(
            session__event=self.event_form.event,
            session__code="BASIC-EDUCATION",
            code="STRATEGIC-DIALOGUE",
        )
        speaker = ConferenceSpeaker.objects.create(
            event=self.event_form.event,
            full_name="Dr. Amina Mushi",
            position_title="Director of Education",
            institution="Ministry of Education, Science and Technology",
        )
        ConferenceProgrammeContributor.objects.create(
            programme_item=programme_item,
            speaker=speaker,
            role=ConferenceProgrammeContributor.Role.MODERATOR,
        )

        response = self.client.get(
            reverse(
                "conferences:public_programme",
                kwargs={"event_slug": self.event_form.event.slug},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Conference programme")
        self.assertContains(response, "Basic Education Session")
        self.assertContains(response, "Strategic dialogue")
        self.assertContains(response, "Dr. Amina Mushi")
        self.assertContains(response, "Moderator")
        self.assertContains(response, "Print programme")

    def test_unpublished_programme_item_is_hidden_from_public(self):
        programme_item = ConferenceProgrammeItem.objects.get(
            session__event=self.event_form.event,
            session__code="STI",
            code="PRIORITY-ACTIONS",
        )
        programme_item.title = "Internal planning item"
        programme_item.is_published = False
        programme_item.save()

        response = self.client.get(
            reverse(
                "conferences:public_programme",
                kwargs={"event_slug": self.event_form.event.slug},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Internal planning item")

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

    def paper_payload(self):
        return {
            "submission_type": ConferencePaper.SubmissionType.ABSTRACT,
            "presentation_format": ConferencePaper.PresentationFormat.ORAL,
            "title": "Digital learning systems for inclusive secondary education",
            "abstract": (
                "This study examines digital learning systems in secondary schools across "
                "Tanzania. It describes the methods, findings, implementation challenges, "
                "practical lessons and recommendations for improving equitable access and "
                "learning outcomes through sustainable education technology investments."
            ),
            "thematic_area": "Basic Education and Digital Learning",
            "keywords": "education, digital learning, inclusion",
            "corresponding_author": "Dr. Amina Mushi",
            "institution": "University of Dodoma",
            "email": "amina.paper@example.test",
            "phone": "+255700000001",
            "co_authors": "Prof. Baraka Juma — University of Dodoma",
            "confirmation": "on",
        }

    def test_public_author_can_submit_and_track_an_abstract(self):
        call = ConferenceCallForPapers.objects.get(event=self.event_form.event)
        response = self.client.post(
            reverse(
                "conferences:paper_submit",
                kwargs={"event_slug": call.event.slug},
            ),
            self.paper_payload(),
        )
        paper = ConferencePaper.objects.get(email="amina.paper@example.test")
        self.assertRedirects(
            response,
            reverse("conferences:paper_status", kwargs={"public_token": paper.public_token}),
        )
        self.assertEqual(paper.status, ConferencePaper.Status.SUBMITTED)
        self.assertTrue(paper.reference_number.startswith("NESIF-2026-ABS-"))
        status_page = self.client.get(response["Location"])
        self.assertContains(status_page, paper.reference_number)
        self.assertContains(status_page, "Digital learning systems")

    def test_full_paper_requires_supported_document(self):
        payload = self.paper_payload()
        payload["submission_type"] = ConferencePaper.SubmissionType.FULL_PAPER
        response = self.client.post(
            reverse(
                "conferences:paper_submit",
                kwargs={"event_slug": self.event_form.event.slug},
            ),
            payload,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upload the document when submitting a full paper")
        self.assertFalse(ConferencePaper.objects.filter(email=payload["email"]).exists())

    def test_manager_can_accept_paper_and_assign_session(self):
        call = ConferenceCallForPapers.objects.get(event=self.event_form.event)
        paper = ConferencePaper.objects.create(call=call, **{
            key: value for key, value in self.paper_payload().items()
            if key not in {"confirmation"}
        })
        session = ConferenceSession.objects.get(event=call.event, code="BASIC-EDUCATION")
        self.client.force_login(self.admin_user)
        response = self.client.post(
            reverse(
                "conferences:paper_review",
                kwargs={"form_id": self.event_form.pk, "paper_id": paper.pk},
            ),
            {
                "decision": ConferencePaper.Status.ACCEPTED,
                "assigned_session": session.pk,
                "decision_message": "Accepted for an oral presentation.",
                "internal_notes": "Strong policy relevance.",
            },
        )
        self.assertEqual(response.status_code, 302)
        paper.refresh_from_db()
        self.assertEqual(paper.status, ConferencePaper.Status.ACCEPTED)
        self.assertEqual(paper.assigned_session, session)
        self.assertEqual(paper.reviewed_by, self.admin_user)
        self.assertTrue(ConferencePaperReview.objects.filter(paper=paper).exists())
        public_status = self.client.get(
            reverse("conferences:paper_status", kwargs={"public_token": paper.public_token})
        )
        self.assertContains(public_status, "Accepted for an oral presentation")
        self.assertNotContains(public_status, "Strong policy relevance")

    def test_participant_cannot_open_paper_review_centre(self):
        self.client.force_login(self.participant_user)
        response = self.client.get(
            reverse("conferences:paper_review_list", kwargs={"form_id": self.event_form.pk})
        )
        self.assertEqual(response.status_code, 403)

    def test_peer_reviewer_can_score_only_assigned_paper(self):
        reviewer_user = User.objects.create_user(
            username="peer-reviewer",
            email="reviewer@example.test",
            password="safe-test-password",
            role=User.Role.REPORT_OFFICER,
        )
        reviewer = ConferenceReviewer.objects.create(
            event=self.event_form.event,
            user=reviewer_user,
            institution="University of Dar es Salaam",
            expertise="Education technology and research methods",
        )
        call = ConferenceCallForPapers.objects.get(event=self.event_form.event)
        paper = ConferencePaper.objects.create(call=call, **{
            key: value for key, value in self.paper_payload().items()
            if key != "confirmation"
        })
        assignment = ConferencePaperReviewAssignment.objects.create(
            paper=paper,
            reviewer=reviewer,
            assigned_by=self.admin_user,
        )
        self.client.force_login(reviewer_user)
        response = self.client.post(
            reverse("conferences:peer_review", kwargs={"assignment_id": assignment.pk}),
            {
                "status": ConferencePaperReviewAssignment.Status.COMPLETED,
                "conflict_reason": "",
                "relevance_score": 5,
                "originality_score": 4,
                "methodology_score": 4,
                "clarity_score": 5,
                "impact_score": 5,
                "recommendation": ConferencePaperReviewAssignment.Recommendation.ACCEPT,
                "comments_to_author": "A strong and relevant contribution.",
                "confidential_comments": "Suitable for the main programme.",
            },
        )
        self.assertEqual(response.status_code, 302)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, ConferencePaperReviewAssignment.Status.COMPLETED)
        self.assertEqual(assignment.average_score, 4.6)
        self.assertIsNotNone(assignment.submitted_at)

    def test_manager_can_assign_reviewer_and_paper_moves_under_review(self):
        reviewer_user = User.objects.create_user(
            username="assigned-reviewer",
            password="safe-test-password",
            role=User.Role.REPORT_OFFICER,
        )
        reviewer = ConferenceReviewer.objects.create(
            event=self.event_form.event,
            user=reviewer_user,
            expertise="Innovation policy",
        )
        call = ConferenceCallForPapers.objects.get(event=self.event_form.event)
        paper = ConferencePaper.objects.create(call=call, **{
            key: value for key, value in self.paper_payload().items()
            if key != "confirmation"
        })
        self.client.force_login(self.admin_user)
        response = self.client.post(
            reverse(
                "conferences:assign_paper_reviewer",
                kwargs={"form_id": self.event_form.pk, "paper_id": paper.pk},
            ),
            {"reviewer": reviewer.pk},
        )
        self.assertEqual(response.status_code, 302)
        paper.refresh_from_db()
        self.assertEqual(paper.status, ConferencePaper.Status.UNDER_REVIEW)
        self.assertTrue(
            ConferencePaperReviewAssignment.objects.filter(
                paper=paper, reviewer=reviewer,
            ).exists()
        )

    def test_unassigned_user_cannot_open_peer_review(self):
        reviewer_user = User.objects.create_user(
            username="restricted-reviewer",
            password="safe-test-password",
            role=User.Role.REPORT_OFFICER,
        )
        reviewer = ConferenceReviewer.objects.create(
            event=self.event_form.event,
            user=reviewer_user,
            expertise="Research",
        )
        call = ConferenceCallForPapers.objects.get(event=self.event_form.event)
        paper = ConferencePaper.objects.create(call=call, **{
            key: value for key, value in self.paper_payload().items()
            if key != "confirmation"
        })
        assignment = ConferencePaperReviewAssignment.objects.create(
            paper=paper, reviewer=reviewer, assigned_by=self.admin_user,
        )
        self.client.force_login(self.participant_user)
        response = self.client.get(
            reverse("conferences:peer_review", kwargs={"assignment_id": assignment.pk})
        )
        self.assertEqual(response.status_code, 403)

    def test_manager_schedules_accepted_paper_and_author_confirms(self):
        call = ConferenceCallForPapers.objects.get(event=self.event_form.event)
        paper = ConferencePaper.objects.create(call=call, **{
            key: value for key, value in self.paper_payload().items()
            if key != "confirmation"
        })
        paper.status = ConferencePaper.Status.ACCEPTED
        paper.save()
        session = ConferenceSession.objects.get(event=call.event, code="BASIC-EDUCATION")
        self.client.force_login(self.admin_user)
        response = self.client.post(
            reverse(
                "conferences:presentation_schedule",
                kwargs={"form_id": self.event_form.pk, "paper_id": paper.pk},
            ),
            {
                "session": session.pk,
                "programme_item": "",
                "presenter_name": "Dr. Amina Mushi",
                "starts_at": "2026-08-17T10:00",
                "ends_at": "2026-08-17T10:20",
                "venue_name": "Main Conference Hall",
                "status": ConferencePresentation.Status.SCHEDULED,
                "manager_notes": "Arrive 20 minutes early.",
            },
        )
        self.assertEqual(response.status_code, 302)
        presentation = ConferencePresentation.objects.get(paper=paper)
        self.client.logout()
        confirmation = self.client.post(
            reverse(
                "conferences:presentation_confirm",
                kwargs={"public_token": paper.public_token},
            ),
            {
                "presenter_name": "Dr. Amina Mushi",
                "presenter_notes": "Confirmed.",
                "confirmation": "on",
            },
        )
        self.assertEqual(confirmation.status_code, 302)
        presentation.refresh_from_db()
        self.assertEqual(presentation.status, ConferencePresentation.Status.CONFIRMED)
        self.assertIsNotNone(presentation.confirmed_at)

    def test_scheduled_accepted_paper_appears_in_public_programme(self):
        call = ConferenceCallForPapers.objects.get(event=self.event_form.event)
        paper = ConferencePaper.objects.create(call=call, **{
            key: value for key, value in self.paper_payload().items()
            if key != "confirmation"
        })
        paper.status = ConferencePaper.Status.ACCEPTED
        paper.save()
        session = ConferenceSession.objects.get(event=call.event, code="STI")
        ConferencePresentation.objects.create(
            paper=paper,
            session=session,
            presenter_name=paper.corresponding_author,
            starts_at=session.starts_at,
            ends_at=session.starts_at + timedelta(minutes=20),
            venue_name="Innovation Hall",
        )
        response = self.client.get(
            reverse("conferences:public_programme", kwargs={"event_slug": call.event.slug})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, paper.title)
        self.assertContains(response, "Accepted paper presentation")
