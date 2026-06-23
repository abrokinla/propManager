import uuid
from django.db import migrations


def backfill_slugs(apps, schema_editor):
    UserProfile = apps.get_model('properties', 'UserProfile')
    for profile in UserProfile.objects.filter(public_slug__isnull=True):
        profile.public_slug = uuid.uuid4().hex[:12]
        profile.save(update_fields=['public_slug'])


class Migration(migrations.Migration):

    dependencies = [
        ('properties', '0013_userprofile_public_slug'),
    ]

    operations = [
        migrations.RunPython(backfill_slugs, migrations.RunPython.noop),
    ]
