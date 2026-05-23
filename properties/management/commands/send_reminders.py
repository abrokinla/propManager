from django.core.management.base import BaseCommand
from properties.services.reminder_service import send_due_reminders


class Command(BaseCommand):
    help = 'Send scheduled reminders for lease expiries and other events'

    def handle(self, *args, **options):
        sent = send_due_reminders()
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} reminder(s)"))
