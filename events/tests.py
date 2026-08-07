from django.test import TestCase

from accounts.models import User

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
