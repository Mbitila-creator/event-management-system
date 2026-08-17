from datetime import timedelta
from io import BytesIO

from openpyxl import load_workbook

from django.core.management import call_command
from django.core import mail
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
    ConferenceGuidingTopic,
    ConferenceGuidingQuestion,
    ConferenceGuidingResponse,
    ConferenceGuidingSubmission,
    ConferenceSpeaker,
    ConferenceReviewer,
    ConferencePresentation,
    ConferencePaperCommunication,
    ConferenceCertificate,
    ConferenceFeedback,
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

    def submit_registration(
        self,
        selected_values=None,
        name="Dr. Amina Mushi",
        extra_answers=None,
    ):
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
        payload = {
            f"question_{questions['Full Name'].pk}": name,
            f"question_{questions['Institution Name'].pk}": "University of Dodoma",
            f"question_{questions['Position / Title'].pk}": "Lecturer",
            f"question_{questions['Email Address'].pk}": "amina@example.test",
            f"question_{questions['Phone Number'].pk}": "+255700000001",
            f"question_{questions['Which session(s) will you attend?'].pk}": selected_values,
        }
        for label, value in (extra_answers or {}).items():
            payload[f"question_{questions[label].pk}"] = value

        response = self.client.post(
            reverse(
                "forms_builder:public_event_form",
                kwargs={
                    "event_slug": self.event_form.event.slug,
                    "form_slug": self.event_form.slug,
                },
            ),
            payload,
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
        self.assertFalse(
            self.event_form.sections.filter(condition_question=question, is_active=True).exists()
        )
        guiding_topics = ConferenceGuidingTopic.objects.filter(
            session__event=self.event_form.event,
            is_active=True,
        )
        self.assertEqual(guiding_topics.count(), 9)
        self.assertEqual(
            ConferenceGuidingQuestion.objects.filter(
                topic__in=guiding_topics,
                is_active=True,
            ).count(),
            33,
        )

    def test_approved_participant_can_save_draft_then_submit_one_session(self):
        submission = self.submit_registration(selected_values=["BASIC_EDUCATION_17_AUG"])
        question = ConferenceGuidingQuestion.objects.filter(
            topic__session__registration_option_value="BASIC_EDUCATION_17_AUG"
        ).first()
        session = question.topic.session
        url = reverse(
            "conferences:participant_session_guiding_questions",
            kwargs={
                "participant_token": submission.participant_token,
                "session_id": session.pk,
            },
        )

        response = self.client.post(url, {
            f"question_{question.pk}": "My draft contribution",
            "action": "draft",
        })

        self.assertEqual(response.status_code, 302)
        progress = ConferenceGuidingSubmission.objects.get(
            submission=submission, session=session
        )
        self.assertEqual(progress.status, ConferenceGuidingSubmission.Status.DRAFT)
        self.assertTrue(
            ConferenceGuidingResponse.objects.filter(
                submission=submission,
                question=question,
                response="My draft contribution",
            ).exists()
        )
        response = self.client.post(url, {
            f"question_{question.pk}": "My final contribution",
            "action": "submit",
        })
        self.assertEqual(response.status_code, 302)
        progress.refresh_from_db()
        self.assertEqual(progress.status, ConferenceGuidingSubmission.Status.SUBMITTED)
        self.assertIsNotNone(progress.submitted_at)
        self.assertEqual(
            submission.conference_guiding_responses.get(question=question).response,
            "My final contribution",
        )

    def test_newly_registered_participant_can_access_guiding_questions(self):
        submission = self.submit_registration(selected_values=["BASIC_EDUCATION_17_AUG"])
        response = self.client.get(reverse(
            "conferences:participant_guiding_questions",
            kwargs={"participant_token": submission.participant_token},
        ))
        self.assertEqual(response.status_code, 200)

    def test_same_name_email_and_phone_cannot_register_twice(self):
        self.submit_registration(
            selected_values=["BASIC_EDUCATION_17_AUG"],
            name="Dr. Amina Mushi",
        )
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
                f"question_{questions['Full Name'].pk}": "  dr.  AMINA mushi ",
                f"question_{questions['Institution Name'].pk}": "Another institution",
                f"question_{questions['Position / Title'].pk}": "Researcher",
                f"question_{questions['Email Address'].pk}": "AMINA@example.test",
                f"question_{questions['Phone Number'].pk}": "+255 700-000-001",
                f"question_{questions['Which session(s) will you attend?'].pk}": [
                    "STI_21_AUG"
                ],
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.json()["duplicate"])
        self.assertEqual(
            FormSubmission.objects.filter(event_form=self.event_form).count(),
            1,
        )
        self.assertIn(
            str(questions["Email Address"].pk),
            response.json()["errors"],
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
        self.assertNotContains(
            response,
            "Shifting to Competency: Strengthening Foundational Learning",
        )

    def test_administrator_can_print_and_download_participant_list(self):
        submission = self.submit_registration(
            selected_values=["BASIC_EDUCATION_17_AUG"],
            name="Dr. Amina Mushi",
        )
        self.submit_registration(
            selected_values=["STI_21_AUG"],
            name="Prof. Baraka Juma",
        )
        basic_session = ConferenceSession.objects.get(
            event=self.event_form.event,
            registration_option_value="BASIC_EDUCATION_17_AUG",
        )
        self.client.force_login(User.objects.get(pk=self.admin_user.pk))

        print_response = self.client.get(reverse(
            "conferences:participant_list_print",
            kwargs={"form_id": self.event_form.pk},
        ), {
            "session": basic_session.pk,
            "status": FormSubmission.ReviewStatus.PENDING,
            "q": "Amina",
        }, follow=True)
        self.assertEqual(print_response.status_code, 200)
        self.assertContains(print_response, "Registered Participants List")
        self.assertContains(print_response, "@page{size:A4 portrait")
        self.assertContains(print_response, "Dr. Amina Mushi")
        self.assertNotContains(print_response, "Prof. Baraka Juma")
        self.assertNotContains(print_response, '<th class="ref">')
        self.assertNotContains(print_response, '<th class="status">')
        self.assertContains(print_response, "Download filtered Excel")

        excel_response = self.client.get(reverse(
            "conferences:participant_list_excel",
            kwargs={"form_id": self.event_form.pk},
        ), {
            "session": basic_session.pk,
            "status": FormSubmission.ReviewStatus.PENDING,
            "q": "Amina",
        }, follow=True)
        self.assertEqual(excel_response.status_code, 200)
        self.assertEqual(
            excel_response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        workbook = load_workbook(BytesIO(excel_response.content))
        sheet = workbook["Registered participants"]
        self.assertEqual(sheet["A1"].value, self.event_form.event.title_en)
        self.assertEqual(sheet["A6"].value, 1)
        self.assertEqual(sheet["B6"].value, submission.reference_number)
        self.assertEqual(sheet["C6"].value, "Dr. Amina Mushi")
        self.assertIsNone(sheet["A7"].value)
        self.assertIn("Basic Education Session", sheet["A4"].value)
        self.assertEqual(sheet.page_setup.orientation, "portrait")

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
        self.assertContains(response, "Print Timetable")
        self.assertContains(response, "Download Timetable")
        self.assertContains(response, "data-print-timetable")
        self.assertContains(response, "data-download-timetable")
        self.assertContains(response, 'data-programme-session="session-')
        self.assertContains(response, 'aria-pressed="false"')
        self.assertContains(response, 'role="region"')
        self.assertContains(
            response,
            'class="conference-programme-print-header"',
            count=ConferenceSession.objects.filter(
                event=self.event_form.event,
                is_active=True,
            ).count(),
        )
        self.assertNotContains(response, "09:00–15:00 · Usagara")
        self.assertContains(
            response,
            " hidden>",
            count=ConferenceSession.objects.filter(
                event=self.event_form.event,
                is_active=True,
            ).count(),
        )
        self.assertContains(
            response,
            '<time class="conference-programme-time">09:30–12:00</time>',
            html=True,
        )

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

    def test_selected_programme_sessions_can_be_downloaded_as_pdf(self):
        sessions = list(
            ConferenceSession.objects.filter(
                event=self.event_form.event,
                is_active=True,
            ).order_by("starts_at")[:2]
        )

        response = self.client.get(
            reverse(
                "conferences:programme_download",
                kwargs={"event_slug": self.event_form.event.slug},
            ),
            {"session": [str(session.pk) for session in sessions]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF"))

        no_selection_response = self.client.get(
            reverse(
                "conferences:programme_download",
                kwargs={"event_slug": self.event_form.event.slug},
            )
        )
        self.assertEqual(no_selection_response.status_code, 400)

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

    def test_manager_sends_logged_author_communication_and_letter(self):
        call = ConferenceCallForPapers.objects.get(event=self.event_form.event)
        paper = ConferencePaper.objects.create(call=call, **{
            key: value for key, value in self.paper_payload().items()
            if key != "confirmation"
        })
        paper.status = ConferencePaper.Status.ACCEPTED
        paper.decision_message = "Accepted following peer review."
        paper.save()
        self.client.force_login(self.admin_user)
        response = self.client.post(
            reverse(
                "conferences:paper_communication",
                kwargs={"form_id": self.event_form.pk, "paper_id": paper.pk},
            ),
            {
                "communication_type": ConferencePaperCommunication.CommunicationType.ACCEPTANCE,
                "recipient_email": paper.email,
                "subject": "Paper acceptance notification",
                "message": "Your paper has been accepted for presentation.",
            },
        )
        self.assertEqual(response.status_code, 302)
        communication = ConferencePaperCommunication.objects.get(paper=paper)
        self.assertEqual(
            communication.delivery_status,
            ConferencePaperCommunication.DeliveryStatus.SENT,
        )
        self.assertIsNotNone(communication.sent_at)
        self.assertEqual(len(mail.outbox), 1)
        letter = self.client.get(
            reverse("conferences:paper_letter", kwargs={"public_token": paper.public_token})
        )
        self.assertContains(letter, "ACCEPTANCE AND PRESENTATION INVITATION")
        self.assertContains(letter, paper.reference_number)
        self.assertContains(letter, "MINISTRY OF EDUCATION, SCIENCE AND TECHNOLOGY")

    def test_certificates_are_generated_only_from_eligible_records(self):
        participant = self.submit_registration()
        participant.review_status = FormSubmission.ReviewStatus.APPROVED
        participant.save()
        unattended = self.submit_registration(name="Dr. Neema Kimaro")
        unattended.review_status = FormSubmission.ReviewStatus.APPROVED
        unattended.save()
        session = ConferenceSession.objects.get(
            event=self.event_form.event,
            registration_option_value="BASIC_EDUCATION_17_AUG",
        )
        ConferenceSessionAttendance.objects.create(
            session=session,
            submission=participant,
            checked_in_by=self.admin_user,
        )
        self.client.force_login(self.admin_user)
        response = self.client.post(
            reverse("conferences:certificate_list", kwargs={"form_id": self.event_form.pk}),
            {"recipient_type": ConferenceCertificate.RecipientType.PARTICIPANT},
        )
        self.assertEqual(response.status_code, 302)
        certificate = ConferenceCertificate.objects.get()
        self.assertEqual(certificate.participant_submission, participant)
        self.assertEqual(certificate.recipient_name, "Dr. Amina Mushi")
        self.assertFalse(
            ConferenceCertificate.objects.filter(participant_submission=unattended).exists()
        )

    def test_delivered_presenter_and_completed_reviewer_receive_certificates(self):
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
            presenter_name="Prof. Asha Mrema",
            starts_at=session.starts_at,
            ends_at=session.starts_at + timedelta(minutes=20),
            venue_name="Innovation Hall",
            status=ConferencePresentation.Status.DELIVERED,
        )
        reviewer_user = User.objects.create_user(
            username="certificate-reviewer",
            first_name="John",
            last_name="Massawe",
            password="safe-test-password",
        )
        reviewer = ConferenceReviewer.objects.create(
            event=call.event,
            user=reviewer_user,
            institution="University of Dar es Salaam",
            expertise="Education technology",
        )
        ConferencePaperReviewAssignment.objects.create(
            paper=paper,
            reviewer=reviewer,
            assigned_by=self.admin_user,
            status=ConferencePaperReviewAssignment.Status.COMPLETED,
            relevance_score=5,
            originality_score=4,
            methodology_score=4,
            clarity_score=5,
            impact_score=5,
            recommendation=ConferencePaperReviewAssignment.Recommendation.ACCEPT,
        )
        self.client.force_login(self.admin_user)
        url = reverse("conferences:certificate_list", kwargs={"form_id": self.event_form.pk})
        self.client.post(url, {"recipient_type": "ALL"})
        self.assertTrue(ConferenceCertificate.objects.filter(
            recipient_type=ConferenceCertificate.RecipientType.PRESENTER,
            paper=paper,
        ).exists())
        self.assertTrue(ConferenceCertificate.objects.filter(
            recipient_type=ConferenceCertificate.RecipientType.REVIEWER,
            reviewer=reviewer,
        ).exists())
        self.client.post(url, {"recipient_type": "ALL"})
        self.assertEqual(ConferenceCertificate.objects.count(), 2)

    def test_certificate_qr_verification_and_revocation(self):
        participant = self.submit_registration()
        participant.review_status = FormSubmission.ReviewStatus.APPROVED
        participant.save()
        session = ConferenceSession.objects.get(
            event=self.event_form.event,
            registration_option_value="BASIC_EDUCATION_17_AUG",
        )
        ConferenceSessionAttendance.objects.create(
            session=session, submission=participant, checked_in_by=self.admin_user,
        )
        self.client.force_login(self.admin_user)
        list_url = reverse(
            "conferences:certificate_list", kwargs={"form_id": self.event_form.pk},
        )
        self.client.post(list_url, {
            "recipient_type": ConferenceCertificate.RecipientType.PARTICIPANT,
        })
        certificate = ConferenceCertificate.objects.get()
        qr = self.client.get(reverse(
            "conferences:certificate_qr",
            kwargs={"verification_token": certificate.verification_token},
        ))
        self.assertEqual(qr.status_code, 200)
        self.assertEqual(qr["Content-Type"], "image/png")
        self.assertTrue(qr.content.startswith(b"\x89PNG"))
        printable = self.client.get(reverse(
            "conferences:certificate_print",
            kwargs={"verification_token": certificate.verification_token},
        ))
        self.assertContains(printable, certificate.certificate_number)
        self.assertContains(printable, "Print / save as PDF")
        verify_url = reverse(
            "conferences:certificate_verify",
            kwargs={"verification_token": certificate.verification_token},
        )
        self.assertContains(self.client.get(verify_url), "Valid conference certificate")
        response = self.client.post(reverse(
            "conferences:certificate_revoke",
            kwargs={"form_id": self.event_form.pk, "certificate_id": certificate.pk},
        ), {"reason": "Issued against an incorrect attendance record."})
        self.assertEqual(response.status_code, 302)
        certificate.refresh_from_db()
        self.assertTrue(certificate.is_revoked)
        self.assertContains(
            self.client.get(verify_url), "Issued against an incorrect attendance record.",
        )

    def test_participant_cannot_access_certificate_management(self):
        self.client.force_login(self.participant_user)
        response = self.client.get(reverse(
            "conferences:certificate_list", kwargs={"form_id": self.event_form.pk},
        ))
        self.assertEqual(response.status_code, 403)

    def feedback_payload(self, **overrides):
        payload = {
            "session": "",
            "overall_rating": "5",
            "content_rating": "4",
            "speakers_rating": "5",
            "organization_rating": "4",
            "venue_rating": "4",
            "would_recommend": "True",
            "most_valuable": "Strategic dialogue and practical examples.",
            "improvements": "Allow more time for participant questions.",
            "additional_comments": "A valuable national forum.",
        }
        payload.update(overrides)
        return payload

    def test_public_conference_feedback_form_accepts_identified_response(self):
        session = ConferenceSession.objects.get(
            event=self.event_form.event,
            code="BASIC-EDUCATION",
        )
        url = reverse(
            "conferences:feedback_submit",
            kwargs={"event_slug": self.event_form.event.slug},
        )
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Conference feedback and evaluation")
        self.assertContains(page, "Basic Education Session")
        response = self.client.post(url, self.feedback_payload(
            session=str(session.pk),
            respondent_name="Dr. Amina Mushi",
            institution="University of Dodoma",
            email="AMINA@EXAMPLE.TEST",
        ))
        self.assertEqual(response.status_code, 302)
        feedback = ConferenceFeedback.objects.get()
        self.assertFalse(feedback.is_anonymous)
        self.assertEqual(feedback.respondent_name, "Dr. Amina Mushi")
        self.assertEqual(feedback.email, "amina@example.test")
        self.assertEqual(feedback.session, session)
        self.assertTrue(feedback.reference_number.startswith("NESIF-2026-FB-"))
        thanks = self.client.get(response.url)
        self.assertContains(thanks, feedback.reference_number)
        self.assertContains(thanks, self.event_form.event.code)

    def test_anonymous_feedback_does_not_store_identity(self):
        url = reverse(
            "conferences:feedback_submit",
            kwargs={"event_slug": self.event_form.event.slug},
        )
        response = self.client.post(url, self.feedback_payload(
            is_anonymous="on",
            respondent_name="Should Not Be Stored",
            institution="Private Institution",
            email="private@example.test",
        ))
        self.assertEqual(response.status_code, 302)
        feedback = ConferenceFeedback.objects.get()
        self.assertTrue(feedback.is_anonymous)
        self.assertEqual(feedback.respondent_name, "")
        self.assertEqual(feedback.institution, "")
        self.assertEqual(feedback.email, "")

    def test_identified_feedback_requires_name_and_valid_ratings(self):
        url = reverse(
            "conferences:feedback_submit",
            kwargs={"event_slug": self.event_form.event.slug},
        )
        response = self.client.post(url, self.feedback_payload(
            respondent_name="",
            overall_rating="7",
        ))
        self.assertEqual(response.status_code, 200)
        self.assertIn("respondent_name", response.context["form"].errors)
        self.assertIn("overall_rating", response.context["form"].errors)
        self.assertFalse(ConferenceFeedback.objects.exists())

    def test_feedback_dashboard_aggregates_and_exports_responses(self):
        ConferenceFeedback.objects.create(
            event=self.event_form.event,
            is_anonymous=True,
            overall_rating=5,
            content_rating=4,
            speakers_rating=5,
            organization_rating=4,
            venue_rating=3,
            would_recommend=True,
            most_valuable="National collaboration",
        )
        ConferenceFeedback.objects.create(
            event=self.event_form.event,
            is_anonymous=False,
            respondent_name="Dr. John Massawe",
            institution="UDSM",
            email="john@example.test",
            overall_rating=3,
            content_rating=4,
            speakers_rating=3,
            organization_rating=2,
            venue_rating=3,
            would_recommend=False,
            improvements="More discussion time",
        )
        self.client.force_login(self.admin_user)
        dashboard_url = reverse(
            "conferences:feedback_dashboard",
            kwargs={"form_id": self.event_form.pk},
        )
        response = self.client.get(dashboard_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["summary"]["total"], 2)
        self.assertEqual(response.context["summary"]["anonymous"], 1)
        self.assertEqual(response.context["summary"]["overall"], 4)
        self.assertEqual(response.context["summary"]["recommend_percent"], 50)
        export = self.client.get(reverse(
            "conferences:feedback_csv",
            kwargs={"form_id": self.event_form.pk},
        ))
        self.assertEqual(export.status_code, 200)
        self.assertIn("text/csv", export["Content-Type"])
        csv_text = export.content.decode("utf-8-sig")
        self.assertIn("Most valuable aspect", csv_text)
        self.assertIn("National collaboration", csv_text)
        self.assertIn("Dr. John Massawe", csv_text)

    def test_feedback_qr_is_png_and_dashboard_is_permission_protected(self):
        qr = self.client.get(reverse(
            "conferences:feedback_qr",
            kwargs={"event_slug": self.event_form.event.slug},
        ))
        self.assertEqual(qr.status_code, 200)
        self.assertEqual(qr["Content-Type"], "image/png")
        self.assertTrue(qr.content.startswith(b"\x89PNG"))
        self.client.force_login(self.participant_user)
        dashboard = self.client.get(reverse(
            "conferences:feedback_dashboard",
            kwargs={"form_id": self.event_form.pk},
        ))
        self.assertEqual(dashboard.status_code, 403)
