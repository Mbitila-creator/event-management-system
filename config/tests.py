import json
from unittest.mock import MagicMock, patch

from django.core.mail import EmailMessage
from django.test import SimpleTestCase, override_settings

from .email_backends import BrevoEmailBackend


@override_settings(
    BREVO_API_KEY="test-api-key",
    BREVO_API_URL="https://api.brevo.test/v3/smtp/email",
    BREVO_TIMEOUT=10,
)
class BrevoEmailBackendTests(SimpleTestCase):
    @patch("config.email_backends.urlopen")
    def test_sends_message_using_brevo_api(self, mocked_urlopen):
        response = MagicMock(status=201)
        response.__enter__.return_value = response
        mocked_urlopen.return_value = response
        message = EmailMessage(
            subject="Registration received",
            body="Your reference is ABC123.",
            from_email="Events Team <events@example.org>",
            to=["Participant <participant@example.org>"],
        )

        delivered = BrevoEmailBackend().send_messages([message])

        self.assertEqual(delivered, 1)
        request = mocked_urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["sender"]["email"], "events@example.org")
        self.assertEqual(payload["to"][0]["email"], "participant@example.org")
        self.assertEqual(payload["subject"], "Registration received")
        self.assertEqual(request.headers["Api-key"], "test-api-key")

    @override_settings(BREVO_API_KEY="")
    def test_missing_api_key_raises_clear_error(self):
        message = EmailMessage(
            subject="Test",
            body="Test",
            from_email="events@example.org",
            to=["participant@example.org"],
        )

        with self.assertRaisesMessage(RuntimeError, "BREVO_API_KEY"):
            BrevoEmailBackend().send_messages([message])

    @override_settings(BREVO_API_KEY="")
    def test_missing_api_key_can_fail_silently(self):
        message = EmailMessage(
            subject="Test",
            body="Test",
            from_email="events@example.org",
            to=["participant@example.org"],
        )

        delivered = BrevoEmailBackend(fail_silently=True).send_messages([message])

        self.assertEqual(delivered, 0)
