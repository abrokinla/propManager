from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('properties', '0004_remove_payment_month_for_remove_tenant_monthly_rent_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='tenant',
            name='monthly_rent',
        ),
        migrations.RemoveField(
            model_name='payment',
            name='month_for',
        ),
    ]
