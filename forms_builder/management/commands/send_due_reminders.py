from django.core.management.base import BaseCommand
from django.utils import timezone

from forms_builder.models import EventReminder
from forms_builder.notifications import process_event_reminder


class Command(BaseCommand):
    help = "Send scheduled event reminders whose sending time has arrived."

    def handle(self, *args, **options):
        due_reminders = EventReminder.objects.filter(
            status=EventReminder.Status.SCHEDULED,
            scheduled_for__lte=timezone.now(),
        ).select_related("event").order_by("scheduled_for")
        processed = 0

        for reminder in due_reminders:
            process_event_reminder(reminder)
            processed += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"Sent reminder {reminder.pk} for {reminder.event.code}."
                )
            )

        self.stdout.write(
            self.style.SUCCESS(f"Processed {processed} due reminder(s).")
        )
