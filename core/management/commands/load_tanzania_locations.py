import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Council, Country, Region


class Command(BaseCommand):
    help = "Load Tanzania regions and councils from the verified CSV file."

    REGION_DATA = [
        ("ARUSHA", "Arusha", "Arusha"),
        ("DAR_ES_SALAAM", "Dar es Salaam", "Dar es Salaam"),
        ("DODOMA", "Dodoma", "Dodoma"),
        ("GEITA", "Geita", "Geita"),
        ("IRINGA", "Iringa", "Iringa"),
        ("KAGERA", "Kagera", "Kagera"),
        ("KATAVI", "Katavi", "Katavi"),
        ("KIGOMA", "Kigoma", "Kigoma"),
        ("KILIMANJARO", "Kilimanjaro", "Kilimanjaro"),
        ("LINDI", "Lindi", "Lindi"),
        ("MANYARA", "Manyara", "Manyara"),
        ("MARA", "Mara", "Mara"),
        ("MBEYA", "Mbeya", "Mbeya"),
        ("MOROGORO", "Morogoro", "Morogoro"),
        ("MTWARA", "Mtwara", "Mtwara"),
        ("MWANZA", "Mwanza", "Mwanza"),
        ("NJOMBE", "Njombe", "Njombe"),
        ("PWANI", "Pwani", "Coast"),
        ("RUKWA", "Rukwa", "Rukwa"),
        ("RUVUMA", "Ruvuma", "Ruvuma"),
        ("SHINYANGA", "Shinyanga", "Shinyanga"),
        ("SIMIYU", "Simiyu", "Simiyu"),
        ("SINGIDA", "Singida", "Singida"),
        ("SONGWE", "Songwe", "Songwe"),
        ("TABORA", "Tabora", "Tabora"),
        ("TANGA", "Tanga", "Tanga"),
        ("KASKAZINI_UNGUJA", "Kaskazini Unguja", "North Unguja"),
        ("KUSINI_UNGUJA", "Kusini Unguja", "South Unguja"),
        ("MJINI_MAGHARIBI", "Mjini Magharibi", "Urban West"),
        ("KASKAZINI_PEMBA", "Kaskazini Pemba", "North Pemba"),
        ("KUSINI_PEMBA", "Kusini Pemba", "South Pemba"),
    ]

    REQUIRED_COLUMNS = {
        "region_code",
        "council_code",
        "name_sw",
        "name_en",
        "council_type",
    }

    @transaction.atomic
    def handle(self, *args, **options):
        country, _ = Country.objects.update_or_create(
            code="TZA",
            defaults={
                "name_sw": "Tanzania",
                "name_en": "Tanzania",
                "phone_code": "+255",
                "is_active": True,
            },
        )

        region_map = self.load_regions(country)
        self.load_councils(region_map)

    def load_regions(self, country):
        region_map = {}
        created_count = 0
        updated_count = 0

        for code, name_sw, name_en in self.REGION_DATA:
            region, created = Region.objects.update_or_create(
                country=country,
                code=code,
                defaults={
                    "name_sw": name_sw,
                    "name_en": name_en,
                    "is_active": True,
                },
            )

            region_map[code] = region

            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Regions completed. Created: {created_count}, "
                f"Updated: {updated_count}"
            )
        )

        return region_map

    def load_councils(self, region_map):
        csv_path = (
            Path(__file__).resolve().parents[2]
            / "data"
            / "tanzania_councils.csv"
        )

        if not csv_path.exists():
            raise CommandError(
                f"Council data file was not found: {csv_path}"
            )

        created_count = 0
        updated_count = 0
        processed_count = 0

        with csv_path.open(
            mode="r",
            encoding="utf-8-sig",
            newline="",
        ) as csv_file:
            reader = csv.DictReader(csv_file)

            if not reader.fieldnames:
                raise CommandError("The council CSV file is empty.")

            missing_columns = (
                self.REQUIRED_COLUMNS - set(reader.fieldnames)
            )

            if missing_columns:
                missing = ", ".join(sorted(missing_columns))
                raise CommandError(
                    f"Missing CSV columns: {missing}"
                )

            valid_types = {
                choice[0] for choice in Council.CouncilType.choices
            }

            for row_number, row in enumerate(reader, start=2):
                region_code = row["region_code"].strip().upper()
                council_code = row["council_code"].strip().upper()
                name_sw = row["name_sw"].strip()
                name_en = row["name_en"].strip()
                council_type = row["council_type"].strip().upper()

                if not all(
                    [
                        region_code,
                        council_code,
                        name_sw,
                        name_en,
                        council_type,
                    ]
                ):
                    raise CommandError(
                        f"Incomplete council data on CSV row "
                        f"{row_number}."
                    )

                region = region_map.get(region_code)

                if region is None:
                    raise CommandError(
                        f"Unknown region code '{region_code}' "
                        f"on CSV row {row_number}."
                    )

                if council_type not in valid_types:
                    raise CommandError(
                        f"Invalid council type '{council_type}' "
                        f"on CSV row {row_number}."
                    )

                _, created = Council.objects.update_or_create(
                    region=region,
                    code=council_code,
                    defaults={
                        "name_sw": name_sw,
                        "name_en": name_en,
                        "council_type": council_type,
                        "is_active": True,
                    },
                )

                processed_count += 1

                if created:
                    created_count += 1
                else:
                    updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Councils completed. Processed: {processed_count}, "
                f"Created: {created_count}, "
                f"Updated: {updated_count}"
            )
        )