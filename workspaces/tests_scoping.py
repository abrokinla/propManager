"""Phase 2 scoping tests.

The point of the refactor is that access flows through organization
membership, not direct ownership. These tests cover the shared-workspace case
(the reason the refactor exists) plus the leak cases that must stay closed.
"""
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from properties.models import (
    MaintenanceRequest,
    Payment,
    Property,
    PropertyAvailability,
    Tenant,
    Unit,
    VisitBooking,
)
from workspaces.models import Organization, OrganizationMembership
from workspaces.services.provisioning import add_member


class SharedWorkspaceTests(TestCase):
    """A member who is not Property.owner must still reach the data."""

    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(username='wsowner', password='pass12345')
        self.member = User.objects.create_user(username='wsmember', password='pass12345')
        self.outsider = User.objects.create_user(username='wsout', password='pass12345')
        self.org = Organization.objects.get(memberships__user=self.owner)
        add_member(self.org, self.member, role='admin', accept=True)
        self.prop = Property.objects.create(
            name='Shared Tower',
            address='A1',
            property_type='Apartment',
            organization=self.org,
            total_units=2,
        )
        self.unit = Unit.objects.create(property=self.prop, unit_number='S001')
        self.tenant = Tenant.objects.create(
            unit=self.unit, name='Shared Tenant', annual_rent=500000
        )

    def test_property_owner_is_denormalized_to_org_owner(self):
        self.assertEqual(self.prop.owner_id, self.owner.id)

    def test_member_sees_property_without_owning_it(self):
        self.client.force_authenticate(user=self.member)
        response = self.client.get('/api/properties/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['name'], 'Shared Tower')

    def test_member_can_open_property_detail(self):
        self.client.force_authenticate(user=self.member)
        response = self.client.get(f'/api/properties/{self.prop.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_outsider_sees_nothing(self):
        self.client.force_authenticate(user=self.outsider)
        self.assertEqual(self.client.get('/api/properties/').data['count'], 0)
        response = self.client.get(f'/api/properties/{self.prop.id}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_member_sees_units(self):
        self.client.force_authenticate(user=self.member)
        self.assertEqual(self.client.get('/api/units/').data['count'], 1)

    def test_member_sees_tenants(self):
        self.client.force_authenticate(user=self.member)
        self.assertEqual(self.client.get('/api/tenants/').data['count'], 1)

    def test_member_sees_payments(self):
        Payment.objects.create(
            tenant=self.tenant,
            amount=500000,
            payment_date='2026-01-05',
            payment_method='Cash',
        )
        self.client.force_authenticate(user=self.member)
        self.assertEqual(self.client.get('/api/payments/').data['count'], 1)

    def test_member_sees_maintenance(self):
        MaintenanceRequest.objects.create(
            unit=self.unit, title='Leak', description='Fixing'
        )
        self.client.force_authenticate(user=self.member)
        self.assertEqual(self.client.get('/api/maintenance/').data['count'], 1)

    def test_member_dashboard_stats_include_shared_property(self):
        self.client.force_authenticate(user=self.member)
        response = self.client.get('/api/dashboard/stats/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_properties'], 1)
        self.assertEqual(response.data['total_units'], 1)

    def test_member_sees_availability_and_bookings(self):
        slot = PropertyAvailability.objects.create(
            property=self.prop, day_of_week=0, start_time='09:00', end_time='17:00'
        )
        VisitBooking.objects.create(
            property=self.prop,
            availability=slot,
            guest_name='Visitor',
            guest_email='visitor@test.com',
            guest_phone='+2348000000000',
            visit_date='2026-01-20',
            visit_time='10:00',
        )
        self.client.force_authenticate(user=self.member)
        self.assertEqual(
            self.client.get('/api/availability/').data['count'], 1
        )
        self.assertEqual(self.client.get('/api/bookings/').data['count'], 1)

    def test_member_can_create_property_in_shared_org(self):
        self.client.force_authenticate(user=self.member)
        response = self.client.post(
            '/api/properties/',
            {'name': 'Member Made', 'address': 'B2', 'property_type': 'Studio'},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Property.objects.get(name='Member Made')
        self.assertEqual(created.organization_id, self.org.id)
        # owner stays the org owner, not the member who created it
        self.assertEqual(created.owner_id, self.owner.id)

    def test_outsider_cannot_create_unit_in_foreign_property(self):
        self.client.force_authenticate(user=self.outsider)
        response = self.client.post('/api/units/', {'property_id': self.prop.id})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_outsider_cannot_create_availability_in_foreign_property(self):
        self.client.force_authenticate(user=self.outsider)
        response = self.client.post(
            '/api/availability/',
            {'property': self.prop.id, 'day_of_week': 0, 'start_time': '09:00', 'end_time': '17:00'},
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unaccepted_member_has_no_access(self):
        pending = User.objects.create_user(username='wspending', password='pass12345')
        OrganizationMembership.objects.create(
            organization=self.org, user=pending, role='staff'
        )
        self.client.force_authenticate(user=pending)
        self.assertEqual(self.client.get('/api/properties/').data['count'], 0)


class AnalyticsScopingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(username='anowner', password='pass12345')
        self.member = User.objects.create_user(username='anmember', password='pass12345')
        self.org = Organization.objects.get(memberships__user=self.owner)
        add_member(self.org, self.member, role='agent', accept=True)
        self.prop = Property.objects.create(
            name='Tracked', address='A1', property_type='House', organization=self.org
        )
        self.unit = Unit.objects.create(property=self.prop, unit_number='T001')
        self.tenant = Tenant.objects.create(unit=self.unit, name='T')
        Payment.objects.create(
            tenant=self.tenant,
            amount=1000,
            payment_date='2026-01-05',
            payment_method='Cash',
        )

    def test_analytics_summary_scoped_to_accessible_properties(self):
        from properties.models import PropertyView

        PropertyView.objects.create(property=self.prop)
        self.client.force_authenticate(user=self.member)
        response = self.client.get('/api/analytics/summary/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_views'], 1)

    def test_analytics_detail_reachable_by_member(self):
        self.client.force_authenticate(user=self.member)
        response = self.client.get(f'/api/analytics/property/{self.prop.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_ai_description_reachable_by_member(self):
        self.client.force_authenticate(user=self.member)
        # Groq may or may not be configured; assert scoping, not the AI result.
        response = self.client.post(
            '/api/ai/generate-description/', {'property_id': self.prop.id}
        )
        self.assertNotEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class DeletionBehaviourTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='delowner', password='pass12345')
        self.other = User.objects.create_user(username='delother', password='pass12345')
        self.org = Organization.objects.get(memberships__user=self.owner)
        self.prop = Property.objects.create(
            name='Doomed', address='A1', property_type='House', organization=self.org
        )

    def test_deleting_user_nulls_owner_but_keeps_property(self):
        self.owner.delete()
        self.prop.refresh_from_db()
        self.assertIsNone(self.prop.owner_id)
        self.assertTrue(Property.objects.filter(pk=self.prop.pk).exists())

    def test_deleting_org_cascades_to_properties(self):
        self.other = User.objects.create_user(username='x', password='pass12345')
        self.org.delete()
        self.assertFalse(Property.objects.filter(pk=self.prop.pk).exists())


class LegacyUnlinkedTests(TestCase):
    """Rows created before the backfill migration ran."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='legacyu', password='pass12345')
        self.orphan = Property.objects.create(
            name='No Org', address='A1', property_type='House', owner=self.user
        )

    def test_owner_still_sees_orphan(self):
        self.client.force_authenticate(user=self.user)
        self.assertEqual(self.client.get('/api/properties/').data['count'], 1)

    def test_orphan_in_dashboard_stats(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get('/api/dashboard/stats/')
        self.assertEqual(response.data['total_properties'], 1)