from django.test import TestCase

from django.core.exceptions import ValidationError

from .models import Council, Country, District, Region, Ward

# Create your tests here.


class WardTests(TestCase):
    def test_council_district_must_belong_to_same_region(self):
        country = Country.objects.create(
            name_sw="Tanzania", name_en="Tanzania", code="TZA",
        )
        region_one = Region.objects.create(
            country=country, name_sw="Tanga", name_en="Tanga", code="02",
        )
        region_two = Region.objects.create(
            country=country, name_sw="Arusha", name_en="Arusha", code="01",
        )
        district = District.objects.create(
            region=region_two, name_sw="Arumeru", name_en="Arumeru", code="ARU",
        )

        with self.assertRaises(ValidationError):
            Council.objects.create(
                region=region_one, district=district,
                name_sw="Jiji la Tanga", name_en="Tanga City", code="TANGA-CC",
            )

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
