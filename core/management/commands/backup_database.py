import sqlite3
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections


class Command(BaseCommand):
    help = "Create a consistent timestamped backup of the SQLite database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            type=Path,
            default=settings.BASE_DIR / "backups",
            help="Directory that will receive the backup file.",
        )

    def handle(self, *args, **options):
        database = connections["default"]
        if database.vendor != "sqlite":
            raise CommandError(
                "backup_database currently supports SQLite databases only."
            )

        output_dir = options["output_dir"].expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup_path = output_dir / f"db-{timestamp}.sqlite3"

        database.ensure_connection()
        with sqlite3.connect(backup_path) as destination:
            database.connection.backup(destination)

        self.stdout.write(
            self.style.SUCCESS(f"Database backup created: {backup_path}")
        )
