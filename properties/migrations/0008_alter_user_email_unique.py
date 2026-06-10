from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('properties', '0007_property_amenities_property_is_published_and_more'),
    ]

    operations = [
        migrations.RunSQL(
            "CREATE UNIQUE INDEX IF NOT EXISTS auth_user_email_uniq ON auth_user (email) WHERE email <> '';",
            "DROP INDEX IF EXISTS auth_user_email_uniq;",
        ),
    ]
