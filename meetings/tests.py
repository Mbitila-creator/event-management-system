from datetime import timedelta
import shutil
import tempfile

from django.core.exceptions import ValidationError
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from events.models import Event, EventCategory, Venue

from .models import (
    Meeting,
    MeetingActionItem,
    MeetingAgendaItem,
    MeetingAttendee,
    MeetingCommunicationLog,
    MeetingDecision,
    MeetingDocument,
    MeetingMinutesReview,
    MeetingResource,
    MeetingResourceBooking,
    MeetingSeries,
    MeetingSeriesAgendaTemplate,
)


class MeetingModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting_category = EventCategory.objects.create(
            name_sw="Kikao",
            name_en="Meeting",
            code="MEETING",
        )
        cls.exhibition_category = EventCategory.objects.create(
            name_sw="Maonesho",
            name_en="Exhibition",
            code="EXHIBITION",
        )
        starts_at = timezone.now() + timedelta(days=7)
        cls.event = Event.objects.create(
            category=cls.meeting_category,
            code="MEET-001",
            title_sw="Kikao cha Menejimenti",
            title_en="Management Meeting",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=2),
        )

    def create_meeting(self, **overrides):
        values = {
            "event": self.event,
            "reference_number": "KM/001/2026",
            "chairperson_name": "Mwenyekiti",
        }
        values.update(overrides)
        return Meeting.objects.create(**values)

    def test_meeting_must_use_meeting_event_category(self):
        starts_at = timezone.now() + timedelta(days=5)
        exhibition = Event.objects.create(
            category=self.exhibition_category,
            code="EXH-001",
            title_sw="Maonesho",
            title_en="Exhibition",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(days=1),
        )
        with self.assertRaises(ValidationError):
            Meeting.objects.create(
                event=exhibition,
                reference_number="EXH-MEET-1",
                chairperson_name="Mwenyekiti",
            )

    def test_invitation_deadline_cannot_follow_meeting_start(self):
        with self.assertRaises(ValidationError):
            self.create_meeting(
                invitation_deadline=self.event.starts_at + timedelta(minutes=1),
            )

    def test_checkin_closing_time_must_follow_opening_time(self):
        opens_at = timezone.now() + timedelta(hours=2)
        with self.assertRaises(ValidationError):
            self.create_meeting(
                checkin_enabled=True,
                checkin_opens_at=opens_at,
                checkin_closes_at=opens_at - timedelta(minutes=1),
            )

    def test_online_meeting_requires_platform_and_joining_link(self):
        with self.assertRaises(ValidationError):
            self.create_meeting(
                attendance_mode=Meeting.AttendanceMode.ONLINE,
            )

    def test_meeting_reference_is_normalized(self):
        meeting = self.create_meeting(reference_number=" km/001/2026 ")
        self.assertEqual(meeting.reference_number, "KM/001/2026")

    def test_internal_attendee_requires_user(self):
        meeting = self.create_meeting()
        with self.assertRaises(ValidationError):
            MeetingAttendee.objects.create(
                meeting=meeting,
                attendee_type=MeetingAttendee.AttendeeType.INTERNAL,
                full_name="Mtumishi",
            )

    def test_internal_attendee_uses_user_identity(self):
        meeting = self.create_meeting()
        user = User.objects.create_user(
            username="meeting.member",
            email="member@example.com",
            first_name="Asha",
            last_name="Juma",
        )
        attendee = MeetingAttendee.objects.create(
            meeting=meeting,
            attendee_type=MeetingAttendee.AttendeeType.INTERNAL,
            user=user,
            full_name=" ",
        )
        self.assertEqual(attendee.full_name, "Asha Juma")
        self.assertEqual(attendee.email, "member@example.com")

    def test_decision_agenda_item_must_belong_to_same_meeting(self):
        meeting = self.create_meeting()
        other_starts_at = timezone.now() + timedelta(days=10)
        other_event = Event.objects.create(
            category=self.meeting_category,
            code="MEET-002",
            title_sw="Kikao Kingine",
            title_en="Another Meeting",
            starts_at=other_starts_at,
            ends_at=other_starts_at + timedelta(hours=1),
        )
        other_meeting = Meeting.objects.create(
            event=other_event,
            reference_number="KM/002/2026",
            chairperson_name="Mwenyekiti",
        )
        other_agenda = MeetingAgendaItem.objects.create(
            meeting=other_meeting,
            item_number=1,
            title_sw="Ajenda",
            title_en="Agenda",
        )
        with self.assertRaises(ValidationError):
            MeetingDecision.objects.create(
                meeting=meeting,
                agenda_item=other_agenda,
                decision_number=1,
                decision_sw="Uamuzi",
            )

    def test_action_uses_responsible_user_name_and_completion_time(self):
        meeting = self.create_meeting()
        user = User.objects.create_user(
            username="action.owner",
            email="owner@example.com",
            first_name="John",
            last_name="Mushi",
        )
        action = MeetingActionItem.objects.create(
            meeting=meeting,
            action_number=1,
            description_sw="Andaa taarifa",
            responsible_user=user,
            status=MeetingActionItem.Status.COMPLETED,
        )
        self.assertEqual(action.responsible_name, "John Mushi")
        self.assertIsNotNone(action.completed_at)

    def test_action_decision_must_belong_to_same_meeting(self):
        meeting = self.create_meeting()
        other_starts_at = timezone.now() + timedelta(days=10)
        other_event = Event.objects.create(
            category=self.meeting_category,
            code="MEET-003",
            title_sw="Kikao cha Tatu",
            title_en="Third Meeting",
            starts_at=other_starts_at,
            ends_at=other_starts_at + timedelta(hours=1),
        )
        other_meeting = Meeting.objects.create(
            event=other_event,
            reference_number="KM/003/2026",
            chairperson_name="Mwenyekiti",
        )
        decision = MeetingDecision.objects.create(
            meeting=other_meeting,
            decision_number=1,
            decision_sw="Uamuzi mwingine",
        )
        with self.assertRaises(ValidationError):
            MeetingActionItem.objects.create(
                meeting=meeting,
                decision=decision,
                action_number=1,
                description_sw="Tekeleza uamuzi",
                responsible_name="Afisa",
            )


class MeetingRolePermissionTests(TestCase):
    def test_event_administrator_has_meeting_permissions(self):
        user = User.objects.create_user(
            username="event.admin",
            email="event.admin@example.com",
            role=User.Role.EVENT_ADMIN,
        )
        self.assertTrue(user.has_perm("meetings.add_meeting"))
        self.assertTrue(user.has_module_perms("meetings"))

    def test_director_has_read_only_meeting_permissions(self):
        user = User.objects.create_user(
            username="director",
            email="director@example.com",
            role=User.Role.DIRECTOR,
        )
        self.assertTrue(user.has_perm("meetings.view_meeting"))
        self.assertFalse(user.has_perm("meetings.change_meeting"))


class MeetingAdministrationTests(TestCase):
    def setUp(self):
        self.administrator = User.objects.create_superuser(
            username="system.admin",
            email="system.admin@example.com",
            password="Strong-Test-Password-2026",
            preferred_language=User.PreferredLanguage.ENGLISH,
        )
        self.client.force_login(self.administrator)

    def test_meeting_links_are_available_on_administration_dashboard(self):
        response = self.client.get(reverse("admin:index"), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("admin:meetings_meeting_changelist"))
        self.assertContains(response, reverse("admin:meetings_meeting_add"))

    def test_meeting_add_page_renders(self):
        response = self.client.get(
            reverse("admin:meetings_meeting_add"),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "id_reference_number")


class MeetingWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = EventCategory.objects.create(
            name_sw="Vikao",
            name_en="Meetings",
            code="MEETING",
        )
        starts_at = timezone.now() + timedelta(days=8)
        cls.event = Event.objects.create(
            category=cls.category,
            code="WORKFLOW-001",
            title_sw="Kikao cha Mfumo",
            title_en="Workflow Meeting",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=2),
            is_public=False,
            registration_enabled=False,
        )
        cls.meeting = Meeting.objects.create(
            event=cls.event,
            reference_number="WK/001/2026",
            chairperson_name="Mwenyekiti wa Kikao",
            quorum_required=2,
        )
        cls.manager = User.objects.create_user(
            username="meeting.manager",
            email="meeting.manager@example.com",
            password="Strong-Test-Password-2026",
            role=User.Role.EVENT_ADMIN,
            preferred_language="en",
        )

    def setUp(self):
        self.client.force_login(self.manager)

    def create_series(self, **overrides):
        values = {
            "code": "MANAGEMENT-MONTHLY",
            "name_sw": "Kikao cha Menejimenti cha Mwezi",
            "name_en": "Monthly Management Meeting",
            "frequency": MeetingSeries.Frequency.MONTHLY,
            "meeting_type": Meeting.MeetingType.MANAGEMENT,
            "default_duration_minutes": 90,
            "chairperson_name": "Mkurugenzi",
            "secretary_name": "Katibu wa Menejimenti",
            "quorum_required": 3,
        }
        values.update(overrides)
        return MeetingSeries.objects.create(**values)

    def test_manager_can_open_meeting_workspace(self):
        response = self.client.get("/en/staff/meetings/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Meetings workspace")
        self.assertContains(response, "Workflow Meeting")

    def test_manager_can_upload_download_and_archive_meeting_document(self):
        media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media_root, ignore_errors=True)
        with override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                f"/en/staff/meetings/{self.meeting.pk}/documents/add/",
                {
                    "document_type": MeetingDocument.DocumentType.AGENDA_PAPER,
                    "title_sw": "Waraka wa ajenda",
                    "title_en": "Agenda paper",
                    "version": "2",
                    "is_confidential": "on",
                    "file": SimpleUploadedFile(
                        "agenda-paper.pdf",
                        b"%PDF-1.4 meeting paper",
                        content_type="application/pdf",
                    ),
                },
            )
            document = MeetingDocument.objects.get(title_en="Agenda paper")
            self.assertRedirects(
                response,
                f"/en/staff/meetings/{self.meeting.pk}/#documents",
                fetch_redirect_response=False,
            )
            self.assertNotEqual(document.file.name, "agenda-paper.pdf")
            self.assertEqual(document.original_filename, "agenda-paper.pdf")
            self.assertEqual(document.version, 2)
            self.assertTrue(document.is_confidential)

            response = self.client.get(
                f"/en/staff/meetings/{self.meeting.pk}/documents/"
                f"{document.pk}/download/",
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["X-Content-Type-Options"], "nosniff")
            self.assertEqual(response["Cache-Control"], "private, no-store")
            self.assertIn(
                'filename="agenda-paper.pdf"',
                response["Content-Disposition"],
            )
            self.assertEqual(b"".join(response.streaming_content), b"%PDF-1.4 meeting paper")

            response = self.client.post(
                f"/en/staff/meetings/{self.meeting.pk}/documents/"
                f"{document.pk}/archive/",
            )
            document.refresh_from_db()
            self.assertRedirects(
                response,
                f"/en/staff/meetings/{self.meeting.pk}/#documents",
                fetch_redirect_response=False,
            )
            self.assertFalse(document.is_active)

    def test_invalid_meeting_document_type_is_rejected(self):
        response = self.client.post(
            f"/en/staff/meetings/{self.meeting.pk}/documents/add/",
            {
                "document_type": MeetingDocument.DocumentType.OTHER,
                "title_sw": "Faili hatarishi",
                "title_en": "Unsafe file",
                "version": "1",
                "file": SimpleUploadedFile("unsafe.exe", b"program"),
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Upload a PDF, Office document, text file, or image.",
        )
        self.assertFalse(MeetingDocument.objects.exists())

    def test_minutes_submission_and_director_approval_lock_the_record(self):
        save_response = self.client.post(
            f"/en/staff/meetings/{self.meeting.pk}/minutes/update/",
            {
                "minutes_sw": "Kumbukumbu za kikao zilizohakikiwa.",
                "minutes_en": "Reviewed meeting minutes.",
                "minutes_status": Meeting.MinutesStatus.APPROVED,
            },
        )
        self.assertEqual(save_response.status_code, 302)
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.minutes_status, Meeting.MinutesStatus.DRAFT)

        submit_response = self.client.post(
            f"/en/staff/meetings/{self.meeting.pk}/minutes/submit/",
        )
        self.assertEqual(submit_response.status_code, 302)
        self.meeting.refresh_from_db()
        self.assertEqual(
            self.meeting.minutes_status,
            Meeting.MinutesStatus.SUBMITTED,
        )
        self.assertTrue(
            MeetingMinutesReview.objects.filter(
                meeting=self.meeting,
                action=MeetingMinutesReview.Action.SUBMITTED,
                created_by=self.manager,
            ).exists()
        )

        locked_response = self.client.post(
            f"/en/staff/meetings/{self.meeting.pk}/minutes/update/",
            {"minutes_sw": "Mabadiliko yasiyoruhusiwa"},
        )
        self.assertEqual(locked_response.status_code, 403)
        self.meeting.refresh_from_db()
        self.assertNotEqual(
            self.meeting.minutes_sw,
            "Mabadiliko yasiyoruhusiwa",
        )

        director = User.objects.create_user(
            username="minutes.director",
            email="minutes.director@example.com",
            role=User.Role.DIRECTOR,
            preferred_language="en",
        )
        self.client.force_login(director)
        approve_response = self.client.post(
            f"/en/staff/meetings/{self.meeting.pk}/minutes/approve/",
            {"comment": "Approved after review."},
        )
        self.assertEqual(approve_response.status_code, 302)
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.minutes_status, Meeting.MinutesStatus.APPROVED)
        self.assertEqual(self.meeting.minutes_approved_by, director)
        self.assertIsNotNone(self.meeting.minutes_approved_at)
        review = MeetingMinutesReview.objects.get(
            meeting=self.meeting,
            action=MeetingMinutesReview.Action.APPROVED,
        )
        self.assertEqual(review.comment, "Approved after review.")

    def test_director_can_return_minutes_and_manager_can_correct_them(self):
        self.meeting.minutes_sw = "Rasimu ya kumbukumbu"
        self.meeting.minutes_status = Meeting.MinutesStatus.SUBMITTED
        self.meeting.save()
        director = User.objects.create_user(
            username="return.director",
            email="return.director@example.com",
            role=User.Role.ASSISTANT_DIRECTOR,
            preferred_language="en",
        )
        self.client.force_login(director)

        missing_reason = self.client.post(
            f"/en/staff/meetings/{self.meeting.pk}/minutes/return/",
            {"comment": ""},
        )
        self.meeting.refresh_from_db()
        self.assertEqual(missing_reason.status_code, 302)
        self.assertEqual(
            self.meeting.minutes_status,
            Meeting.MinutesStatus.SUBMITTED,
        )

        return_response = self.client.post(
            f"/en/staff/meetings/{self.meeting.pk}/minutes/return/",
            {"comment": "Correct the attendance total."},
        )
        self.assertEqual(return_response.status_code, 302)
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.minutes_status, Meeting.MinutesStatus.RETURNED)
        self.assertTrue(
            MeetingMinutesReview.objects.filter(
                meeting=self.meeting,
                action=MeetingMinutesReview.Action.RETURNED,
                comment="Correct the attendance total.",
            ).exists()
        )

        self.client.force_login(self.manager)
        correction_response = self.client.post(
            f"/en/staff/meetings/{self.meeting.pk}/minutes/update/",
            {
                "minutes_sw": "Rasimu iliyosahihishwa",
                "minutes_en": "Corrected draft",
            },
        )
        self.meeting.refresh_from_db()
        self.assertEqual(correction_response.status_code, 302)
        self.assertEqual(self.meeting.minutes_status, Meeting.MinutesStatus.DRAFT)
        self.assertEqual(self.meeting.minutes_en, "Corrected draft")

    def test_only_minutes_approver_can_approve_or_reopen_minutes(self):
        self.meeting.minutes_sw = "Kumbukumbu"
        self.meeting.minutes_status = Meeting.MinutesStatus.SUBMITTED
        self.meeting.save()
        manager_response = self.client.post(
            f"/en/staff/meetings/{self.meeting.pk}/minutes/approve/",
            {},
        )
        self.assertEqual(manager_response.status_code, 403)

        director = User.objects.create_user(
            username="reopen.director",
            email="reopen.director@example.com",
            role=User.Role.DIRECTOR,
            preferred_language="en",
        )
        self.client.force_login(director)
        self.client.post(
            f"/en/staff/meetings/{self.meeting.pk}/minutes/approve/",
            {},
        )
        reopen_response = self.client.post(
            f"/en/staff/meetings/{self.meeting.pk}/minutes/reopen/",
            {"comment": "A material correction is required."},
        )
        self.assertEqual(reopen_response.status_code, 302)
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.minutes_status, Meeting.MinutesStatus.RETURNED)
        self.assertIsNone(self.meeting.minutes_approved_by)
        self.assertTrue(
            MeetingMinutesReview.objects.filter(
                meeting=self.meeting,
                action=MeetingMinutesReview.Action.REOPENED,
            ).exists()
        )

    def test_read_only_meeting_user_can_download_but_cannot_upload(self):
        media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media_root, ignore_errors=True)
        director = User.objects.create_user(
            username="document.director",
            email="document.director@example.com",
            role=User.Role.DIRECTOR,
            preferred_language="en",
        )
        with override_settings(MEDIA_ROOT=media_root):
            document = MeetingDocument.objects.create(
                meeting=self.meeting,
                document_type=MeetingDocument.DocumentType.MEETING_NOTICE,
                title_sw="Taarifa ya kikao",
                file=SimpleUploadedFile("notice.pdf", b"meeting notice"),
            )
            self.client.force_login(director)
            download_response = self.client.get(
                f"/en/staff/meetings/{self.meeting.pk}/documents/"
                f"{document.pk}/download/",
            )
            self.assertEqual(download_response.status_code, 200)
            upload_response = self.client.post(
                f"/en/staff/meetings/{self.meeting.pk}/documents/add/",
                {},
            )
            self.assertEqual(upload_response.status_code, 403)

    def test_user_without_meeting_access_cannot_download_document(self):
        media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media_root, ignore_errors=True)
        officer = User.objects.create_user(
            username="document.registration",
            email="document.registration@example.com",
            role=User.Role.REGISTRATION_OFFICER,
            preferred_language="en",
        )
        with override_settings(MEDIA_ROOT=media_root):
            document = MeetingDocument.objects.create(
                meeting=self.meeting,
                title_sw="Waraka wa siri",
                file=SimpleUploadedFile("confidential.pdf", b"confidential"),
            )
            self.client.force_login(officer)
            response = self.client.get(
                f"/en/staff/meetings/{self.meeting.pk}/documents/"
                f"{document.pk}/download/",
            )
            self.assertEqual(response.status_code, 403)

    def test_manager_can_view_meeting_calendar(self):
        month = timezone.localdate(self.event.starts_at).strftime("%Y-%m")
        response = self.client.get(
            "/en/staff/meetings/calendar/",
            {"month": month},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Meeting calendar")
        self.assertContains(response, "Workflow Meeting")

    def test_manager_can_create_meeting_series(self):
        response = self.client.post("/en/staff/meetings/series/new/", {
            "code": "TECH-MONTHLY",
            "name_sw": "Kikao cha Kiufundi",
            "name_en": "Technical Meeting",
            "description_sw": "Maelezo",
            "description_en": "Description",
            "frequency": MeetingSeries.Frequency.MONTHLY,
            "meeting_type": Meeting.MeetingType.TECHNICAL,
            "attendance_mode": Meeting.AttendanceMode.IN_PERSON,
            "default_duration_minutes": "120",
            "chairperson_name": "Mkurugenzi",
            "secretary_name": "Katibu",
            "quorum_required": "4",
            "objectives_sw": "Kufuatilia utekelezaji",
            "objectives_en": "Monitor implementation",
            "is_active": "on",
        })
        series = MeetingSeries.objects.get(code="TECH-MONTHLY")
        self.assertRedirects(
            response,
            f"/en/staff/meetings/series/{series.pk}/",
            fetch_redirect_response=False,
        )
        self.assertEqual(series.default_duration_minutes, 120)

    def test_series_occurrence_copies_agenda_and_participants(self):
        series = self.create_series()
        MeetingSeriesAgendaTemplate.objects.create(
            series=series,
            item_number=1,
            title_sw="Mapitio ya utekelezaji",
            title_en="Implementation review",
            allocated_minutes=30,
        )
        self.meeting.series = series
        self.meeting.save()
        source_attendee = MeetingAttendee.objects.create(
            meeting=self.meeting,
            full_name="Asha Mjumbe",
            email="asha.series@example.com",
            preferred_language="en",
            response_status=MeetingAttendee.ResponseStatus.ACCEPTED,
            attendance_status=MeetingAttendee.AttendanceStatus.PRESENT,
        )
        starts_at = timezone.localtime(timezone.now() + timedelta(days=30))
        response = self.client.post(
            f"/en/staff/meetings/series/{series.pk}/schedule/",
            {
                "code": "SERIES-002",
                "reference_number": "SER/002/2026",
                "title_sw": "Kikao cha Pili",
                "title_en": "Second Meeting",
                "starts_at": starts_at.strftime("%Y-%m-%dT%H:%M"),
                "status": Event.Status.DRAFT,
                "copy_participants": "on",
            },
        )
        occurrence = Meeting.objects.get(reference_number="SER/002/2026")
        self.assertRedirects(
            response,
            f"/en/staff/meetings/{occurrence.pk}/",
            fetch_redirect_response=False,
        )
        self.assertEqual(occurrence.series, series)
        self.assertEqual(
            occurrence.event.ends_at - occurrence.event.starts_at,
            timedelta(minutes=90),
        )
        self.assertEqual(occurrence.agenda_items.count(), 1)
        copied = occurrence.attendees.get(email=source_attendee.email)
        self.assertEqual(
            copied.response_status,
            MeetingAttendee.ResponseStatus.INVITED,
        )
        self.assertEqual(
            copied.attendance_status,
            MeetingAttendee.AttendanceStatus.NOT_MARKED,
        )

    def test_meeting_pack_is_printable(self):
        response = self.client.get(
            f"/en/staff/meetings/{self.meeting.pk}/print/",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Meeting pack")
        self.assertContains(response, self.meeting.reference_number)
        self.assertContains(response, "window.print()")

    def test_action_report_marks_overdue_items(self):
        MeetingActionItem.objects.create(
            meeting=self.meeting,
            action_number=1,
            description_sw="Andaa taarifa",
            description_en="Prepare report",
            responsible_name="Afisa Mipango",
            due_date=timezone.localdate() - timedelta(days=1),
            status=MeetingActionItem.Status.PENDING,
        )
        response = self.client.get(
            "/en/staff/meetings/reports/actions/",
            {"status": "OVERDUE"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Prepare report")
        self.assertContains(response, "Overdue")

    def test_action_report_csv_is_downloadable_and_spreadsheet_safe(self):
        MeetingActionItem.objects.create(
            meeting=self.meeting,
            action_number=1,
            description_sw="=HATARI()",
            description_en="=DANGEROUS()",
            responsible_name="@Officer",
            due_date=timezone.localdate() + timedelta(days=2),
        )
        response = self.client.get(
            "/en/staff/meetings/reports/actions/export/",
            {"status": "ALL"},
        )
        content = response.content.decode("utf-8-sig")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("'=DANGEROUS()", content)
        self.assertIn("'@Officer", content)

    def test_manager_can_create_event_and_meeting_in_one_workflow(self):
        starts_at = timezone.localtime(timezone.now() + timedelta(days=12))
        response = self.client.post("/en/staff/meetings/new/", {
            "code": "WORKFLOW-002",
            "reference_number": "WK/002/2026",
            "title_sw": "Kikao Kipya",
            "title_en": "New Meeting",
            "description_sw": "Maelezo",
            "description_en": "Description",
            "organizer_name_sw": "Wizara",
            "organizer_name_en": "Ministry",
            "starts_at": starts_at.strftime("%Y-%m-%dT%H:%M"),
            "ends_at": (starts_at + timedelta(hours=3)).strftime(
                "%Y-%m-%dT%H:%M"
            ),
            "status": Event.Status.DRAFT,
            "meeting_type": Meeting.MeetingType.TECHNICAL,
            "attendance_mode": Meeting.AttendanceMode.IN_PERSON,
            "chairperson_name": "Mwenyekiti Mpya",
            "secretary_name": "Katibu",
            "quorum_required": "3",
            "objectives_sw": "Kujadili utekelezaji",
            "objectives_en": "Discuss implementation",
        })
        created = Meeting.objects.get(reference_number="WK/002/2026")
        self.assertRedirects(
            response,
            f"/en/staff/meetings/{created.pk}/",
            fetch_redirect_response=False,
        )
        self.assertEqual(created.event.code, "WORKFLOW-002")
        self.assertFalse(created.event.registration_enabled)
        self.assertFalse(created.event.qr_checkin_enabled)

    def test_manager_can_build_agenda_decisions_and_actions(self):
        agenda_response = self.client.post(
            f"/en/staff/meetings/{self.meeting.pk}/agenda/add/",
            {
                "item_number": "1",
                "title_sw": "Ufunguzi",
                "title_en": "Opening",
                "presenter_name": "Mwenyekiti",
                "allocated_minutes": "10",
            },
        )
        self.assertEqual(agenda_response.status_code, 302)
        agenda = self.meeting.agenda_items.get(item_number=1)

        decision_response = self.client.post(
            f"/en/staff/meetings/{self.meeting.pk}/decisions/add/",
            {
                "agenda_item": agenda.pk,
                "decision_number": "1",
                "decision_sw": "Taarifa iandaliwe",
                "decision_en": "Prepare the report",
                "status": MeetingDecision.Status.APPROVED,
            },
        )
        self.assertEqual(decision_response.status_code, 302)
        decision = self.meeting.decisions.get(decision_number=1)

        action_response = self.client.post(
            f"/en/staff/meetings/{self.meeting.pk}/actions/add/",
            {
                "decision": decision.pk,
                "action_number": "1",
                "description_sw": "Andaa taarifa",
                "description_en": "Prepare report",
                "responsible_name": "Afisa Mipango",
                "due_date": (timezone.localdate() + timedelta(days=5)).isoformat(),
                "status": MeetingActionItem.Status.PENDING,
                "progress_notes": "",
            },
        )
        self.assertEqual(action_response.status_code, 302)
        self.assertTrue(self.meeting.action_items.filter(action_number=1).exists())

    def test_invitation_email_and_public_response_workflow(self):
        attendee = MeetingAttendee.objects.create(
            meeting=self.meeting,
            full_name="Asha Mjumbe",
            email="asha@example.com",
            preferred_language="en",
        )
        with self.settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        ):
            response = self.client.post(
                f"/en/staff/meetings/{self.meeting.pk}/participants/"
                f"{attendee.pk}/invite/",
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(str(attendee.response_token), mail.outbox[0].body)
        attendee.refresh_from_db()
        self.assertIsNotNone(attendee.invitation_sent_at)
        self.assertTrue(
            MeetingCommunicationLog.objects.filter(
                attendee=attendee,
                communication_type=MeetingCommunicationLog.CommunicationType.INVITATION,
                delivery_status=MeetingCommunicationLog.DeliveryStatus.SENT,
            ).exists()
        )

        self.client.logout()
        public_response = self.client.post(
            f"/en/meetings/invitations/{attendee.response_token}/",
            {"response_status": MeetingAttendee.ResponseStatus.ACCEPTED},
        )
        self.assertEqual(public_response.status_code, 200)
        self.assertContains(public_response, "Your response has been recorded")
        attendee.refresh_from_db()
        self.assertEqual(
            attendee.response_status,
            MeetingAttendee.ResponseStatus.ACCEPTED,
        )
        self.assertIsNotNone(attendee.responded_at)

    def test_online_meeting_access_is_in_invitation_and_secure_response_page(self):
        self.meeting.attendance_mode = Meeting.AttendanceMode.ONLINE
        self.meeting.online_platform = Meeting.OnlinePlatform.MICROSOFT_TEAMS
        self.meeting.online_join_url = "https://teams.example.com/join/meeting-001"
        self.meeting.online_meeting_id = "987 654 321"
        self.meeting.online_passcode = "Secure-2026"
        self.meeting.online_instructions_sw = "Jiunge dakika tano kabla."
        self.meeting.online_instructions_en = "Join five minutes early."
        self.meeting.save()
        attendee = MeetingAttendee.objects.create(
            meeting=self.meeting,
            full_name="Online Participant",
            email="online.participant@example.com",
            preferred_language="en",
        )
        with self.settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        ):
            response = self.client.post(
                f"/en/staff/meetings/{self.meeting.pk}/participants/"
                f"{attendee.pk}/invite/",
            )
        self.assertEqual(response.status_code, 302)
        self.assertIn(self.meeting.online_join_url, mail.outbox[0].body)
        self.assertIn("Microsoft Teams", mail.outbox[0].body)
        self.assertIn("Secure-2026", mail.outbox[0].body)

        self.client.logout()
        response = self.client.post(
            f"/en/meetings/invitations/{attendee.response_token}/",
            {"response_status": MeetingAttendee.ResponseStatus.ACCEPTED},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Join online meeting")
        self.assertContains(response, self.meeting.online_join_url)
        self.assertContains(response, "987 654 321")

    def test_online_series_copies_access_details_to_new_occurrence(self):
        series = self.create_series(
            code="ONLINE-MONTHLY",
            attendance_mode=Meeting.AttendanceMode.ONLINE,
            online_platform=Meeting.OnlinePlatform.ZOOM,
            online_join_url="https://zoom.example.com/j/123456",
            online_meeting_id="123456",
            online_passcode="Monthly-Access",
            online_instructions_en="Use your official name.",
        )
        starts_at = timezone.localtime(timezone.now() + timedelta(days=45))
        response = self.client.post(
            f"/en/staff/meetings/series/{series.pk}/schedule/",
            {
                "code": "ONLINE-002",
                "reference_number": "ONL/002/2026",
                "title_sw": "Kikao cha Mtandaoni",
                "title_en": "Online Meeting",
                "starts_at": starts_at.strftime("%Y-%m-%dT%H:%M"),
                "status": Event.Status.DRAFT,
            },
        )
        self.assertEqual(response.status_code, 302)
        occurrence = Meeting.objects.get(reference_number="ONL/002/2026")
        self.assertEqual(occurrence.attendance_mode, Meeting.AttendanceMode.ONLINE)
        self.assertEqual(occurrence.online_platform, Meeting.OnlinePlatform.ZOOM)
        self.assertEqual(occurrence.online_join_url, series.online_join_url)
        self.assertEqual(occurrence.online_passcode, "Monthly-Access")

    def test_meeting_workflow_blocks_an_overlapping_venue_booking(self):
        venue = Venue.objects.create(name="Boardroom One")
        self.event.venue = venue
        self.event.save()
        starts_at = timezone.localtime(self.event.starts_at + timedelta(minutes=30))
        response = self.client.post(
            "/en/staff/meetings/new/",
            {
                "code": "VENUE-CLASH",
                "reference_number": "VC/001/2026",
                "title_sw": "Kikao Kinachogongana",
                "title_en": "Clashing Meeting",
                "starts_at": starts_at.strftime("%Y-%m-%dT%H:%M"),
                "ends_at": (starts_at + timedelta(hours=1)).strftime(
                    "%Y-%m-%dT%H:%M"
                ),
                "venue": venue.pk,
                "status": Event.Status.DRAFT,
                "meeting_type": Meeting.MeetingType.MANAGEMENT,
                "attendance_mode": Meeting.AttendanceMode.IN_PERSON,
                "chairperson_name": "Mwenyekiti",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "This venue is already booked during the selected time.",
        )
        self.assertFalse(Event.objects.filter(code="VENUE-CLASH").exists())

    def test_resource_confirmation_prevents_overbooking(self):
        resource = MeetingResource.objects.create(
            code="PROJECTOR",
            name_sw="Projektor",
            name_en="Projector",
            total_quantity=2,
        )
        booking_response = self.client.post(
            f"/en/staff/meetings/{self.meeting.pk}/resources/add/",
            {"resource": resource.pk, "quantity": "2", "notes": "Main hall"},
        )
        self.assertEqual(booking_response.status_code, 302)
        booking = MeetingResourceBooking.objects.get(meeting=self.meeting)
        self.assertEqual(booking.status, MeetingResourceBooking.Status.REQUESTED)

        confirm_response = self.client.post(
            f"/en/staff/meetings/{self.meeting.pk}/resources/"
            f"{booking.pk}/update/",
            {"action": "CONFIRM"},
        )
        self.assertEqual(confirm_response.status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.status, MeetingResourceBooking.Status.CONFIRMED)
        self.assertEqual(booking.confirmed_by, self.manager)

        other_event = Event.objects.create(
            category=self.category,
            code="RESOURCE-OVERLAP",
            title_sw="Kikao Kingine",
            title_en="Another Meeting",
            starts_at=self.event.starts_at + timedelta(minutes=15),
            ends_at=self.event.ends_at + timedelta(minutes=15),
        )
        other_meeting = Meeting.objects.create(
            event=other_event,
            reference_number="RES/002/2026",
            chairperson_name="Mwenyekiti",
        )
        other_booking = MeetingResourceBooking.objects.create(
            meeting=other_meeting,
            resource=resource,
            quantity=1,
        )
        response = self.client.post(
            f"/en/staff/meetings/{other_meeting.pk}/resources/"
            f"{other_booking.pk}/update/",
            {"action": "CONFIRM"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "This resource is not available in the requested quantity",
        )
        other_booking.refresh_from_db()
        self.assertEqual(
            other_booking.status,
            MeetingResourceBooking.Status.REQUESTED,
        )

    def test_manager_can_create_resource_from_resource_register(self):
        response = self.client.post(
            "/en/staff/meetings/resources/new/",
            {
                "code": "MIC-01",
                "name_sw": "Kipaza sauti",
                "name_en": "Microphone",
                "total_quantity": "8",
                "storage_location": "Store A",
                "is_active": "on",
            },
        )
        self.assertRedirects(
            response,
            "/en/staff/meetings/resources/",
            fetch_redirect_response=False,
        )
        resource = MeetingResource.objects.get(code="MIC-01")
        self.assertEqual(resource.total_quantity, 8)

    def test_manager_can_send_pending_invitations_in_bulk(self):
        pending = MeetingAttendee.objects.create(
            meeting=self.meeting,
            full_name="Asha Pending",
            email="pending@example.com",
            preferred_language="en",
        )
        already_sent = MeetingAttendee.objects.create(
            meeting=self.meeting,
            full_name="Juma Sent",
            email="sent@example.com",
            invitation_sent_at=timezone.now(),
        )
        with self.settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        ):
            response = self.client.post(
                f"/en/staff/meetings/{self.meeting.pk}/"
                "invitations/send-pending/",
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        pending.refresh_from_db()
        self.assertIsNotNone(pending.invitation_sent_at)
        self.assertFalse(
            MeetingCommunicationLog.objects.filter(attendee=already_sent).exists()
        )

    def test_manager_can_send_attendance_reminder(self):
        attendee = MeetingAttendee.objects.create(
            meeting=self.meeting,
            full_name="Neema Mjumbe",
            email="neema@example.com",
            preferred_language="en",
        )
        with self.settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        ):
            response = self.client.post(
                f"/en/staff/meetings/{self.meeting.pk}/participants/"
                f"{attendee.pk}/remind/",
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("confirm whether you will attend", mail.outbox[0].body)
        self.assertIn(str(attendee.response_token), mail.outbox[0].body)
        self.assertTrue(
            MeetingCommunicationLog.objects.filter(
                attendee=attendee,
                communication_type=MeetingCommunicationLog.CommunicationType.RSVP_REMINDER,
            ).exists()
        )

    def test_failed_delivery_is_recorded_in_communication_history(self):
        attendee = MeetingAttendee.objects.create(
            meeting=self.meeting,
            full_name="Delivery Failure",
            email="failure@example.com",
            preferred_language="en",
        )
        with self.settings(EMAIL_BACKEND="missing.email.Backend"):
            response = self.client.post(
                f"/en/staff/meetings/{self.meeting.pk}/participants/"
                f"{attendee.pk}/invite/",
            )
        self.assertEqual(response.status_code, 302)
        communication = MeetingCommunicationLog.objects.get(attendee=attendee)
        self.assertEqual(
            communication.delivery_status,
            MeetingCommunicationLog.DeliveryStatus.FAILED,
        )
        self.assertTrue(communication.error_message)

    def test_manager_can_send_action_deadline_reminder(self):
        owner = User.objects.create_user(
            username="action.reminder.owner",
            email="john@example.com",
            first_name="John",
            last_name="Officer",
            preferred_language="en",
        )
        action = MeetingActionItem.objects.create(
            meeting=self.meeting,
            action_number=1,
            description_sw="Andaa taarifa",
            description_en="Prepare the report",
            responsible_user=owner,
            responsible_name="",
            due_date=timezone.localdate() + timedelta(days=2),
        )
        with self.settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        ):
            response = self.client.post(
                f"/en/staff/meetings/{self.meeting.pk}/actions/"
                f"{action.pk}/remind/",
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Prepare the report", mail.outbox[0].body)
        communication = MeetingCommunicationLog.objects.get(action_item=action)
        self.assertEqual(
            communication.communication_type,
            MeetingCommunicationLog.CommunicationType.ACTION_REMINDER,
        )
        detail = self.client.get(f"/en/staff/meetings/{self.meeting.pk}/")
        self.assertContains(detail, "Communication history")
        self.assertContains(detail, "john@example.com")

    def test_attendance_officer_can_record_attendance_but_not_manage_meeting(self):
        officer = User.objects.create_user(
            username="meeting.attendance",
            email="meeting.attendance@example.com",
            role=User.Role.ATTENDANCE_OFFICER,
            preferred_language="en",
        )
        attendee = MeetingAttendee.objects.create(
            meeting=self.meeting,
            full_name="Juma Mjumbe",
            response_status=MeetingAttendee.ResponseStatus.ACCEPTED,
        )
        self.client.force_login(officer)
        detail = self.client.get(f"/en/staff/meetings/{self.meeting.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, "Add agenda item")
        update = self.client.post(
            f"/en/staff/meetings/{self.meeting.pk}/participants/"
            f"{attendee.pk}/update/",
            {"attendance_status": MeetingAttendee.AttendanceStatus.PRESENT},
        )
        self.assertEqual(update.status_code, 302)
        attendee.refresh_from_db()
        self.assertEqual(
            attendee.attendance_status,
            MeetingAttendee.AttendanceStatus.PRESENT,
        )
        self.assertEqual(
            attendee.response_status,
            MeetingAttendee.ResponseStatus.ACCEPTED,
        )
        self.assertEqual(attendee.checked_in_by, officer)
        self.assertEqual(
            attendee.checkin_method,
            MeetingAttendee.CheckinMethod.MANUAL,
        )
        create_attempt = self.client.get("/en/staff/meetings/new/")
        self.assertEqual(create_attempt.status_code, 403)

    def test_secure_qr_pass_checks_in_participant_once(self):
        self.meeting.checkin_enabled = True
        self.meeting.save()
        attendee = MeetingAttendee.objects.create(
            meeting=self.meeting,
            full_name="Asha Mjumbe",
            organization="MoEST",
            response_status=MeetingAttendee.ResponseStatus.ACCEPTED,
        )
        officer = User.objects.create_user(
            username="qr.attendance",
            email="qr.attendance@example.com",
            role=User.Role.ATTENDANCE_OFFICER,
            preferred_language="en",
        )
        self.client.force_login(officer)
        pass_response = self.client.get(
            reverse("meetings:attendee_pass", args=[self.meeting.pk, attendee.pk]),
        )
        self.assertEqual(pass_response.status_code, 200)
        self.assertContains(pass_response, "data:image/png;base64,")

        scan_url = reverse(
            "meetings:attendee_checkin",
            args=[attendee.response_token],
        )
        first_scan = self.client.get(f"{scan_url}?auto=1")
        self.assertContains(first_scan, "Participant checked in successfully")
        attendee.refresh_from_db()
        self.assertEqual(
            attendee.attendance_status,
            MeetingAttendee.AttendanceStatus.PRESENT,
        )
        self.assertEqual(attendee.checked_in_by, officer)
        self.assertEqual(attendee.checkin_method, MeetingAttendee.CheckinMethod.QR)
        first_time = attendee.checked_in_at

        second_scan = self.client.get(f"{scan_url}?auto=1")
        self.assertContains(second_scan, "Participant already checked in")
        attendee.refresh_from_db()
        self.assertEqual(attendee.checked_in_at, first_time)

    def test_declined_participant_and_closed_window_cannot_check_in(self):
        self.meeting.checkin_enabled = True
        self.meeting.save()
        declined = MeetingAttendee.objects.create(
            meeting=self.meeting,
            full_name="Declined Member",
            response_status=MeetingAttendee.ResponseStatus.DECLINED,
        )
        declined_url = reverse(
            "meetings:attendee_checkin",
            args=[declined.response_token],
        )
        response = self.client.get(f"{declined_url}?auto=1")
        self.assertContains(response, "Check-in not allowed")
        declined.refresh_from_db()
        self.assertIsNone(declined.checked_in_at)

        self.meeting.checkin_closes_at = timezone.now() - timedelta(minutes=1)
        self.meeting.save()
        accepted = MeetingAttendee.objects.create(
            meeting=self.meeting,
            full_name="Late Member",
            response_status=MeetingAttendee.ResponseStatus.ACCEPTED,
        )
        closed_url = reverse(
            "meetings:attendee_checkin",
            args=[accepted.response_token],
        )
        response = self.client.get(f"{closed_url}?auto=1")
        self.assertContains(response, "The meeting check-in window is closed.")
        accepted.refresh_from_db()
        self.assertIsNone(accepted.checked_in_at)

    def test_ordinary_participant_cannot_use_staff_qr_scanner(self):
        self.meeting.checkin_enabled = True
        self.meeting.save()
        attendee = MeetingAttendee.objects.create(
            meeting=self.meeting,
            full_name="Protected Participant",
            response_status=MeetingAttendee.ResponseStatus.ACCEPTED,
        )
        participant_user = User.objects.create_user(
            username="meeting.participant",
            email="meeting.participant@example.com",
            role=User.Role.PARTICIPANT,
        )
        self.client.force_login(participant_user)
        scan = self.client.get(
            reverse("meetings:attendee_checkin", args=[attendee.response_token]),
            follow=True,
        )
        attendee_pass = self.client.get(
            reverse("meetings:attendee_pass", args=[self.meeting.pk, attendee.pk]),
            follow=True,
        )
        self.assertEqual(scan.status_code, 403)
        self.assertEqual(attendee_pass.status_code, 403)
        attendee.refresh_from_db()
        self.assertIsNone(attendee.checked_in_at)

    def test_invitation_response_displays_qr_pass_and_csv_has_audit_data(self):
        self.meeting.checkin_enabled = True
        self.meeting.save()
        attendee = MeetingAttendee.objects.create(
            meeting=self.meeting,
            full_name="CSV Participant",
            email="csv@example.com",
        )
        response = self.client.post(
            reverse("meetings:invitation_response", args=[attendee.response_token]),
            {"response_status": MeetingAttendee.ResponseStatus.ACCEPTED},
        )
        self.assertContains(response, "Meeting check-in pass")
        self.assertContains(response, "data:image/png;base64,")

        attendee.attendance_status = MeetingAttendee.AttendanceStatus.PRESENT
        attendee.checked_in_at = timezone.now()
        attendee.checked_in_by = self.manager
        attendee.checkin_method = MeetingAttendee.CheckinMethod.QR
        attendee.save()
        self.client.force_login(self.manager)
        export = self.client.get(
            reverse("meetings:attendance_register_csv", args=[self.meeting.pk]),
        )
        self.assertEqual(export.status_code, 200)
        csv_body = export.content.decode("utf-8-sig")
        self.assertIn("CSV Participant", csv_body)
        self.assertIn("QR scan", csv_body)
        self.assertIn("meeting.manager", csv_body)

    def test_registration_officer_cannot_access_meeting_workspace(self):
        officer = User.objects.create_user(
            username="registration.only",
            email="registration.only@example.com",
            role=User.Role.REGISTRATION_OFFICER,
            preferred_language="en",
        )
        self.client.force_login(officer)
        response = self.client.get("/en/staff/meetings/")
        self.assertEqual(response.status_code, 403)
        report = self.client.get("/en/staff/meetings/reports/actions/")
        self.assertEqual(report.status_code, 403)
