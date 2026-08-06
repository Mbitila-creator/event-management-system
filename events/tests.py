from django.test import TestCase

# Create your tests here.


class PublicNavigationTests(TestCase):
    def test_public_navigation_links_to_registration_status(self):
        response = self.client.get("/en/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Registration Status")
        self.assertContains(response, "/en/registration-status/")
        self.assertContains(response, "← Back")
        self.assertContains(response, "Exit")
