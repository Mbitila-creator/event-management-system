from datetime import timedelta
from io import BytesIO
from zipfile import ZipFile

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from docx import Document
from openpyxl import Workbook
from PIL import Image

from accounts.models import User
from events.models import Event, EventCategory, SpecialEventParticipant
from events.services import import_special_event_participants

# Create your tests here.


class PublicNavigationTests(TestCase):
    def test_public_navigation_links_to_registration_status(self):
        response = self.client.get("/en/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Registration Status")
        self.assertContains(response, "/en/registration-status/")
        self.assertContains(response, "← Back")
        self.assertContains(response, "Exit")

    def test_staff_modules_are_displayed_below_available_events(self):
        user = User.objects.create_user(
            username="event.navigation",
            password="Strong-Test-Password-2026",
            role=User.Role.EVENT_ADMIN,
            preferred_language=User.PreferredLanguage.ENGLISH,
        )
        self.client.force_login(user)

        response = self.client.get("/en/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="available-events"')
        self.assertContains(response, 'class="module-launcher"')
        self.assertContains(response, "Exhibitions")
        self.assertContains(response, "/en/staff/meetings/")
        self.assertNotContains(response, "meetings-link")


class SpecialEventParticipantQRTests(TestCase):
    password = "Strong-Test-Password-2026"

    def setUp(self):
        self.user = User.objects.create_user(
            username="special.event.admin",
            email="special-admin@example.test",
            password=self.password,
            role=User.Role.EVENT_ADMIN,
            preferred_language=User.PreferredLanguage.ENGLISH,
        )
        self.special_category = EventCategory.objects.create(
            code="SPECIAL_EVENT",
            name_sw="Tukio Maalum",
            name_en="Special Event",
            slug="special-event",
        )
        self.other_category = EventCategory.objects.create(
            code="TRAINING",
            name_sw="Mafunzo",
            name_en="Training",
            slug="training",
        )
        now = timezone.now()
        self.event = Event.objects.create(
            category=self.special_category,
            code="WATAFITI-2026",
            title_sw="Tukio la Watafiti",
            title_en="Researchers Special Event",
            starts_at=now + timedelta(days=2),
            ends_at=now + timedelta(days=3),
            status=Event.Status.PUBLISHED,
            is_public=True,
        )
        self.other_event = Event.objects.create(
            category=self.other_category,
            code="TRAINING-2026",
            title_sw="Mafunzo",
            title_en="Training",
            starts_at=now + timedelta(days=2),
            ends_at=now + timedelta(days=3),
        )

    def workbook_upload(self, rows_by_sheet=None):
        rows_by_sheet = rows_by_sheet or {
            "AWAMU_2": [
                (1, "Mtafiti Mmoja", "Taasisi A", "Utafiti A", "Kilimo"),
                (2, "Jina Linalofanana", "Taasisi B", "Utafiti B", "Afya"),
            ],
            "AWAMU_3": [
                (1, "Jina Linalofanana", "Taasisi C", "Utafiti C", "Elimu"),
            ],
        }
        workbook = Workbook()
        workbook.remove(workbook.active)
        for title, rows in rows_by_sheet.items():
            sheet = workbook.create_sheet(title)
            number_header = "Na." if title == "AWAMU_3" else "Na"
            sheet.append([number_header, "JINA LA MTAFITI", "TAASISI", "UTAFITI", "NYANJA"])
            for row in rows:
                sheet.append(row)
        output = BytesIO()
        workbook.save(output)
        workbook.close()
        return SimpleUploadedFile(
            "participants.xlsx",
            output.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_model_rejects_participant_for_non_special_event(self):
        participant = SpecialEventParticipant(
            event=self.other_event,
            source_sheet="AWAMU_2",
            source_number="1",
            full_name="Wrong Category",
        )
        with self.assertRaises(ValidationError):
            participant.full_clean()

    def test_excel_import_creates_each_sheet_row_with_a_distinct_token(self):
        result = import_special_event_participants(
            event=self.event,
            uploaded_file=self.workbook_upload(),
            user=self.user,
        )
        self.assertEqual(result.created, 3)
        self.assertEqual(result.sheets, 2)
        participants = SpecialEventParticipant.objects.filter(event=self.event)
        self.assertEqual(participants.count(), 3)
        duplicated_names = participants.filter(full_name="Jina Linalofanana")
        self.assertEqual(duplicated_names.count(), 2)
        self.assertEqual(len(set(duplicated_names.values_list("verification_token", flat=True))), 2)

    def test_reimport_updates_exact_row_and_preserves_qr_token(self):
        import_special_event_participants(
            event=self.event,
            uploaded_file=self.workbook_upload({
                "AWAMU_2": [(1, "Mtafiti", "Taasisi A", "Utafiti A", "Kilimo")],
            }),
            user=self.user,
        )
        original = SpecialEventParticipant.objects.get()
        original_token = original.verification_token
        result = import_special_event_participants(
            event=self.event,
            uploaded_file=self.workbook_upload({
                "AWAMU_2": [(1, "Mtafiti", "Taasisi Mpya", "Utafiti A", "Kilimo")],
            }),
            user=self.user,
        )
        original.refresh_from_db()
        self.assertEqual(result.updated, 1)
        self.assertEqual(SpecialEventParticipant.objects.count(), 1)
        self.assertEqual(original.institution, "Taasisi Mpya")
        self.assertEqual(original.verification_token, original_token)

    def test_public_scan_displays_only_the_matching_row(self):
        first = SpecialEventParticipant.objects.create(
            event=self.event,
            source_sheet="AWAMU_2",
            source_number="4",
            full_name="Mtafiti Sahihi",
            institution="Taasisi Sahihi",
            research_title="Utafiti Sahihi",
            research_field="Afya",
        )
        SpecialEventParticipant.objects.create(
            event=self.event,
            source_sheet="AWAMU_2",
            source_number="5",
            full_name="Mtafiti Mwingine",
            research_title="Utafiti Mwingine",
        )
        response = self.client.get(reverse(
            "events:special_event_participant_verify",
            kwargs={"token": first.verification_token},
        ))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mtafiti Sahihi")
        self.assertContains(response, "Taasisi Sahihi")
        self.assertContains(response, "Utafiti Sahihi")
        self.assertContains(response, "Jina la Mtafiti:")
        self.assertContains(response, "Nyanja:")
        self.assertContains(response, "© MoEST 2026.")
        self.assertNotContains(response, "Mtafiti Mwingine")
        self.assertNotContains(response, "Registration Status")
        self.assertNotContains(response, "Phase / worksheet")
        self.assertNotContains(response, "Row number")

    def test_qr_endpoint_returns_png_without_numeric_record_id_in_url(self):
        participant = SpecialEventParticipant.objects.create(
            event=self.event,
            source_sheet="AWAMU_3",
            source_number="8",
            full_name="Mtafiti QR",
        )
        url = reverse(
            "events:special_event_participant_qr",
            kwargs={"token": participant.verification_token},
        )
        self.assertIn(str(participant.verification_token), url)
        self.assertNotIn(f"/{participant.pk}/", url)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertTrue(response.content.startswith(b"\x89PNG"))

    def test_participant_card_download_returns_paste_ready_png(self):
        participant = SpecialEventParticipant.objects.create(
            event=self.event,
            source_sheet="AWAMU_2",
            source_number="12",
            full_name="Mtafiti wa Kadi",
            institution="Taasisi ya Majaribio",
        )
        response = self.client.get(reverse(
            "events:special_event_participant_card_download",
            kwargs={"token": participant.verification_token},
        ))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertIn("attachment;", response["Content-Disposition"])
        image = Image.open(BytesIO(response.content))
        self.assertEqual(image.format, "PNG")
        self.assertEqual(image.size, (1600, 760))

    def test_qr_and_text_sections_download_as_separate_png_files(self):
        participant = SpecialEventParticipant.objects.create(
            event=self.event,
            source_sheet="AWAMU_2",
            source_number="13",
            full_name="Mtafiti wa Picha Tofauti",
            institution="Taasisi ya Majaribio",
        )
        downloads = (
            ("events:special_event_participant_qr_download", (1000, 1000)),
            ("events:special_event_participant_text_download", (1200, 560)),
        )
        for route_name, expected_size in downloads:
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(
                    route_name,
                    kwargs={"token": participant.verification_token},
                ))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Type"], "image/png")
                self.assertIn("attachment;", response["Content-Disposition"])
                image = Image.open(BytesIO(response.content))
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.size, expected_size)

    def test_staff_can_download_all_participant_cards_as_zip(self):
        for number in ("1", "2"):
            SpecialEventParticipant.objects.create(
                event=self.event,
                source_sheet="AWAMU_3",
                source_number=number,
                source_row_index=int(number) + 1,
                full_name=f"Mtafiti {number}",
                institution="Taasisi",
            )
        url = reverse("events:special_event_participant_cards_zip")
        self.assertEqual(self.client.get(f"{url}?event={self.event.pk}").status_code, 302)

        self.client.force_login(self.user)
        response = self.client.get(f"{url}?event={self.event.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        self.assertIn("attachment;", response["Content-Disposition"])
        with ZipFile(BytesIO(response.content)) as archive:
            card_names = [name for name in archive.namelist() if name.endswith(".png")]
            self.assertEqual(len(card_names), 6)
            self.assertEqual(len([name for name in card_names if "/qr-only/" in name]), 2)
            self.assertEqual(len([name for name in card_names if "/text-only/" in name]), 2)
            self.assertEqual(len([name for name in card_names if "/combined-cards/" in name]), 2)
            self.assertTrue(archive.read(card_names[0]).startswith(b"\x89PNG"))

    def test_staff_can_download_one_editable_word_file_with_separate_qr_images(self):
        for number in ("1", "2", "3"):
            SpecialEventParticipant.objects.create(
                event=self.event,
                source_sheet="AWAMU_2",
                source_number=number,
                source_row_index=int(number) + 1,
                full_name=f"Mtafiti wa Word {number}",
                institution=f"Taasisi {number}",
            )
        url = reverse("events:special_event_participant_cards_word")
        self.assertEqual(self.client.get(f"{url}?event={self.event.pk}").status_code, 302)

        self.client.force_login(self.user)
        response = self.client.get(f"{url}?event={self.event.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertIn("attachment;", response["Content-Disposition"])
        document = Document(BytesIO(response.content))
        self.assertEqual(len(document.inline_shapes), 3)
        self.assertEqual(len(document.tables), 3)
        document_text = "\n".join(
            paragraph.text
            for table in document.tables
            for row in table.rows
            for cell in row.cells
            for paragraph in cell.paragraphs
        )
        self.assertIn("Mtafiti wa Word 1", document_text)
        self.assertIn("Mtafiti wa Word 3", document_text)

    def test_staff_list_and_import_require_events_permissions(self):
        list_url = reverse("events:special_event_participant_list")
        import_url = reverse("events:special_event_participant_import")
        anonymous_response = self.client.get(list_url)
        self.assertEqual(anonymous_response.status_code, 302)

        participant_user = User.objects.create_user(
            username="ordinary.participant",
            email="ordinary-participant@example.test",
            password=self.password,
            role=User.Role.PARTICIPANT,
        )
        self.client.force_login(participant_user)
        self.assertNotEqual(self.client.get(list_url).status_code, 200)
        self.assertNotEqual(self.client.get(import_url).status_code, 200)

        self.client.force_login(self.user)
        SpecialEventParticipant.objects.create(
            event=self.event,
            source_sheet="AWAMU_2",
            source_number="1",
            full_name="Mtafiti wa Kupakua",
        )
        response = self.client.get(f"{list_url}?event={self.event.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Participant QR records")
        self.assertContains(response, "Download editable Word cards")
        self.assertNotContains(response, "Download QR only")
        self.assertNotContains(response, "Download text only")

    def test_import_view_rejects_non_special_event(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("events:special_event_participant_import"),
            {"event": self.other_event.pk, "workbook": self.workbook_upload()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select a valid choice")
        self.assertFalse(SpecialEventParticipant.objects.exists())
