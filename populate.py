#!/usr/bin/env python
"""
PropManager seed script — creates demo users and data for local development.
Run: cd /home/araoye/Documents/Github/propmanager && source env/bin/activate && python populate.py
"""
import os, sys, django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'propmanager.settings')
sys.path.insert(0, os.path.dirname(__file__))
django.setup()

from django.contrib.auth.models import User
from properties.models import Property, Unit, Tenant, Payment, MaintenanceRequest
import random
from datetime import date, timedelta

def run():
    print("🧹 Clearing existing data...")
    MaintenanceRequest.objects.all().delete()
    Payment.objects.all().delete()
    Tenant.objects.all().delete()
    Unit.objects.all().delete()
    Property.objects.all().delete()
    User.objects.filter(is_superuser=False).delete()

    # ── Create Owner ──────────────────────────────────────────────
    print("👤 Creating owner: demo_owner")
    owner = User.objects.create_user(
        username='demo_owner',
        email='owner@propmanager.test',
        password='demo12345',
        first_name='Ada',
        last_name='Okafor',
    )
    owner.profile.role = 'owner'
    owner.profile.phone = '+2348012345678'
    owner.profile.company_name = 'Ada Properties Ltd'
    owner.profile.save()

    # ── Create Manager (standalone, not yet invited) ──────────────
    print("👤 Creating manager: demo_manager")
    manager = User.objects.create_user(
        username='demo_manager',
        email='manager@propmanager.test',
        password='demo12345',
        first_name='Chidi',
        last_name='Eze',
    )
    manager.profile.role = 'manager'
    manager.profile.phone = '+2348098765432'
    manager.profile.company_name = ''
    manager.profile.save()

    # ── Create Properties ─────────────────────────────────────────
    print("🏢 Creating properties...")
    properties = []
    property_data = [
        ('Sunrise Apartments', '12 Victoria Island, Lagos', 'apartment', 6),
        ('Green Court Estate', '45 Lekki Phase 1, Lagos', 'estate', 8),
        ('Marina Heights', '8 Marina Road, Lagos', 'commercial', 4),
    ]
    for name, address, ptype, unit_count in property_data:
        p = Property.objects.create(
            owner=owner, name=name, address=address,
            property_type=ptype, description=f'A beautiful {ptype} in Lagos.',
        )
        properties.append((p, unit_count))

    # ── Create Units ───────────────────────────────────────────────
    print("🚪 Creating units...")
    unit_counter = 100
    for prop, count in properties:
        for i in range(1, count + 1):
            Unit.objects.create(
                property=prop,
                unit_number=str(unit_counter + i),
                bedrooms=random.choice([1, 2, 3, 3, 4]),
                bathrooms=random.choice([1, 1, 2, 2, 3]),
                toilets=random.choice([1, 1, 2, 2, 3]),
                size_sqft=random.choice([800, 1200, 1500, 2000, 2500]),
                price_rent=random.choice([150000, 200000, 250000, 350000, 500000, 750000]),
                price_sale=0,
                status=random.choice(['available', 'occupied', 'occupied', 'maintenance']),
            )
        unit_counter += 100

    # ── Create Tenants ─────────────────────────────────────────────
    print("👥 Creating tenants...")
    first_names = ['Tunde', 'Ngozi', 'Emeka', 'Amina', 'Femi', 'Blessing', 'Yusuf', 'Chioma']
    last_names = ['Balogun', 'Adeyemi', 'Obi', 'Ibrahim', 'Ogundimu', 'Nwosu', 'Abdullahi', 'Okonkwo']
    all_units = list(Unit.objects.filter(status='occupied'))
    for i, unit in enumerate(all_units[:8]):
        Tenant.objects.create(
            unit=unit,
            name=f'{first_names[i]} {last_names[i]}',
            email=f'tenant{i}@example.com',
            phone=f'+23480{random.randint(10000000, 99999999)}',
            address='',
            monthly_rent=unit.price_rent or 200000,
            lease_start_date=date(2025, 1, 1) + timedelta(days=random.randint(0, 365)),
            lease_expiry_date=date(2026, 1, 1) + timedelta(days=random.randint(0, 365)),
            move_in_date=date(2025, 1, 15) + timedelta(days=random.randint(0, 365)),
            is_active=True,
        )

    # ── Create Payments ────────────────────────────────────────────
    print("💰 Creating payments...")
    tenants = list(Tenant.objects.all())
    methods = ['bank_transfer', 'cash', 'ussd', 'card']
    for tenant in tenants:
        for m in range(1, random.randint(2, 5)):
            Payment.objects.create(
                tenant=tenant,
                amount=tenant.monthly_rent,
                payment_date=date(2025, m, random.randint(1, 28)),
                payment_method=random.choice(methods),
                month_for=f'{m:02d}/2025',
                notes='',
            )

    # ── Create Maintenance Requests ────────────────────────────────
    print("🔧 Creating maintenance requests...")
    statuses = ['open', 'in_progress', 'completed', 'closed']
    priorities = ['low', 'medium', 'high', 'urgent']
    titles = ['Leaking faucet', 'Broken AC', 'Electrical fault', 'Door lock issue', 'Pest control']
    for unit in Unit.objects.filter(status='occupied')[:5]:
        MaintenanceRequest.objects.create(
            unit=unit,
            title=random.choice(titles),
            description='Needs urgent attention.',
            status=random.choice(statuses),
            priority=random.choice(priorities),
        )

    # ── Summary ────────────────────────────────────────────────────
    print("\n✅ Seed data created successfully!")
    print(f"   Users:       {User.objects.count()}  (owner: demo_owner, manager: demo_manager)")
    print(f"   Properties:  {Property.objects.count()}")
    print(f"   Units:       {Unit.objects.count()}")
    print(f"   Tenants:     {Tenant.objects.count()}")
    print(f"   Payments:    {Payment.objects.count()}")
    print(f"   Maintenance: {MaintenanceRequest.objects.count()}")
    print(f"\n🔑 Login credentials:")
    print(f"   Owner:   demo_owner / demo12345")
    print(f"   Manager: demo_manager / demo12345")


if __name__ == '__main__':
    run()
