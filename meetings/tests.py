from datetime import timedelta

from django.core.exceptions import ValidationError
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
