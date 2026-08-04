from django.test import TestCase

from .models import Council, Country, Region, Ward

# Create your tests here.


class WardTests(TestCase):
    def test_ward_is_attached_to_council(self):
        country = Country.objects.create(
            name_sw="Tanzania", name_en="Tanzania", code="TZA",
        )
        region = Region.objects.create(
            country=country, name_sw="Tanga", name_en="Tanga", code="02",
        )
        council = Council.objects.create(
            region=region, name_sw="Jiji la Tanga", name_en="Tanga City",
            code="TANGA-CC",
        )
        ward = Ward.objects.create(
            council=council, name_sw="Usagara", name_en="Usagara", code="01",
        )
        self.assertEqual(ward.council, council)
        self.assertTrue(ward.slug)
