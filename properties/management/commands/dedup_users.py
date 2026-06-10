from django.db.models import Count
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Deduplicate User records with the same email (prefer tenant-linked users)'

    def handle(self, *args, **options):
        duplicates = (
            User.objects.values('email')
            .annotate(cnt=Count('id'))
            .filter(cnt__gt=1)
        )
        total = duplicates.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS('No duplicate emails found.'))
            return

        removed = 0
        for row in duplicates:
            email = row['email']
            users = User.objects.filter(email=email).order_by('date_joined')
            best = None
            for u in users:
                if hasattr(u, 'tenant_profile') and u.tenant_profile:
                    best = u
                    break
            if not best:
                for u in users:
                    if hasattr(u, 'profile'):
                        best = u
                        break
            if not best:
                best = users.first()

            for u in users:
                if u.id == best.id:
                    continue
                if hasattr(u, 'tenant_profile') and u.tenant_profile:
                    u.tenant_profile.user = best
                    u.tenant_profile.save(update_fields=['user'])
                if hasattr(u, 'profile'):
                    u.profile.delete()
                u.delete()
                removed += 1

        self.stdout.write(self.style.SUCCESS(f"Cleaned up {removed} duplicate user(s) across {total} email(s)"))
