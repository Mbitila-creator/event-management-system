from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from events.models import Event, EventCategory

from .models import (
    Meeting,
    MeetingActionItem,
    MeetingAgendaItem,
    MeetingAttendee,
    MeetingCommunicationLog,
    MeetingDecision,
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

    def test_manager_can_open_meeting_workspace(self):
        response = self.client.get("/en/staff/meetings/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Meetings workspace")
        self.assertContains(response, "Workflow Meeting")

    def test_manager_can_view_meeting_calendar(self):
        month = timezone.localdate(self.event.starts_at).strftime("%Y-%m")
        response = self.client.get(
            "/en/staff/meetings/calendar/",
            {"month": month},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Meeting calendar")
        self.assertContains(response, "Workflow Meeting")

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
        create_attempt = self.client.get("/en/staff/meetings/new/")
        self.assertEqual(create_attempt.status_code, 403)

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
