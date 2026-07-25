from django.test import TestCase

# Create your tests here.
from types import SimpleNamespace

from django.test import RequestFactory, SimpleTestCase, override_settings

from .services import (
    generate_qr_png,
    public_form_path,
    public_form_url,
    safe_spreadsheet_value,
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
