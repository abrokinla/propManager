from django.core.management.base import BaseCommand
from properties.models import Property, Unit
from properties.utils import generate_unit_prefix


class Command(BaseCommand):
    help = 'Create Unit records for existing Properties that have none'

    def handle(self, *args, **options):
        qs = Property.objects.filter(units__isnull=True).distinct()
        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS('No properties missing units.'))
            return

        created = 0
        for prop in qs:
            if prop.units.exists():
                continue
            count = prop.total_units or 0
            if count == 0:
                self.stdout.write(self.style.WARNING(f"  {prop.name} — total_units is 0, skipping"))
                continue
            prefix = generate_unit_prefix(prop.name)
            units = []
            for i in range(1, count + 1):
                units.append(Unit(property=prop, unit_number=f"{prefix}{i:03d}"))
            Unit.objects.bulk_create(units)
            created += count
            self.stdout.write(f"  {prop.name} → {prop.total_units} units ({prefix}...)")

        self.stdout.write(self.style.SUCCESS(
            f"Backfilled {created} unit(s) across {total} propert(ies)"
        ))
