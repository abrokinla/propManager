import uuid
from django.core.management.base import BaseCommand
from properties.models import UserProfile


class Command(BaseCommand):
    help = 'Generate public_slug for existing UserProfiles that lack one'

    def handle(self, *args, **options):
        profiles = UserProfile.objects.filter(public_slug__isnull=True)
        count = 0
        for profile in profiles:
            profile.public_slug = uuid.uuid4().hex[:12]
            profile.save(update_fields=['public_slug'])
            count += 1
        self.stdout.write(self.style.SUCCESS(f'Backfilled {count} agent slug(s)'))
