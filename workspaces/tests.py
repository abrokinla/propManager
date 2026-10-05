from django.contrib.auth.models import User
from django.test import TestCase

from properties.models import Property
from workspaces.models import (
    AgentKYC,
    Organization,
    OrganizationMembership,
    PropertyMembership,
    Subscription,
)
from workspaces.services.provisioning import (
    add_member,
    get_organization,
    get_subscription,
    promote_to_team,
    provision_workspace,
)


class ProvisioningTests(TestCase):
    def test_signal_creates_personal_workspace(self):
        user = User.objects.create_user(username='siguser', password='pass12345')
        org = Organization.objects.get(memberships__user=user)
        self.assertEqual(org.kind, 'personal')
        self.assertEqual(org.track, 'owner')
        self.assertEqual(org.currency, 'USD')

    def test_signal_accepts_membership(self):
        user = User.objects.create_user(username='sigaccept', password='pass12345')
        membership = OrganizationMembership.objects.get(user=user)
        self.assertIsNotNone(membership.accepted_at)
        self.assertEqual(membership.role, 'owner')

    def test_signal_creates_free_subscription(self):
        user = User.objects.create_user(username='sigsub', password='pass12345')
        sub = Subscription.objects.get(organization__memberships__user=user)
        self.assertEqual(sub.plan, 'owner_free')
        self.assertEqual(sub.interval, 'month')
        self.assertEqual(sub.status, 'active')

    def test_signal_creates_kyc_record(self):
        user = User.objects.create_user(username='sigkyc', password='pass12345')
        kyc = AgentKYC.objects.get(user=user)
        self.assertEqual(kyc.status, 'unsubmitted')

    def test_provisioning_is_idempotent(self):
        user = User.objects.create_user(username='idem', password='pass12345')
        first = Organization.objects.filter(memberships__user=user).count()
        second = provision_workspace(user).pk
        third = provision_workspace(user).pk
        self.assertEqual(first, 1)
        self.assertEqual(second, third)
        self.assertEqual(Organization.objects.filter(memberships__user=user).count(), 1)

    def test_provisioning_honours_track(self):
        user = User.objects.create_user(username='agentuser', password='pass12345')
        org = provision_workspace(user, track='agent')
        self.assertEqual(org.track, 'agent')
        self.assertEqual(get_subscription(user).plan, 'agent_free')

    def test_resaving_user_does_not_duplicate_org(self):
        user = User.objects.create_user(username='resave', password='pass12345')
        user.first_name = 'Changed'
        user.save()
        self.assertEqual(Organization.objects.filter(memberships__user=user).count(), 1)

    def test_org_slug_is_unique(self):
        u1 = User.objects.create_user(username='slug1', password='pass12345')
        u2 = User.objects.create_user(username='slug2', password='pass12345')
        u1.first_name = 'Same Name'
        u2.first_name = 'Same Name'
        u1.save()
        u2.save()
        slugs = set(Organization.objects.values_list('slug', flat=True))
        self.assertEqual(len(slugs), Organization.objects.count())

    def test_get_organization_backfills_missing(self):
        user = User.objects.create_user(username='nobackfill', password='pass12345')
        OrganizationMembership.objects.all().delete()
        org = get_organization(user)
        self.assertIsNotNone(org)

    def test_get_subscription_returns_free_tier(self):
        user = User.objects.create_user(username='getsub', password='pass12345')
        self.assertEqual(get_subscription(user).plan, 'owner_free')


class MembershipTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='mowner', password='pass12345')
        self.member = User.objects.create_user(username='mmember', password='pass12345')
        self.org = Organization.objects.get(memberships__user=self.owner)

    def test_add_member_and_promote_to_team(self):
        membership = add_member(self.org, self.member, role='staff')
        self.org.refresh_from_db()
        self.assertEqual(membership.role, 'staff')
        self.assertIsNone(membership.accepted_at)
        self.assertEqual(self.org.kind, 'team')

    def test_add_member_accepted(self):
        membership = add_member(self.org, self.member, role='admin', accept=True)
        self.assertIsNotNone(membership.accepted_at)

    def test_add_member_updates_existing_role(self):
        add_member(self.org, self.member, role='staff')
        membership = add_member(self.org, self.member, role='viewer')
        self.assertEqual(membership.role, 'viewer')
        self.assertEqual(
            OrganizationMembership.objects.filter(organization=self.org, user=self.member).count(),
            1,
        )

    def test_promote_to_team_is_noop_when_already_team(self):
        add_member(self.org, self.member, role='staff')
        self.org.refresh_from_db()
        self.assertEqual(promote_to_team(self.org).kind, 'team')

    def test_membership_accept_is_idempotent(self):
        membership = add_member(self.org, self.member, role='staff', accept=True)
        first = membership.accepted_at
        membership.accept()
        self.assertEqual(membership.accepted_at, first)


class PropertyOrganizationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='powner', password='pass12345')
        self.org = Organization.objects.get(memberships__user=self.owner)

    def test_property_inherits_org_owner(self):
        prop = Property.objects.create(
            name='Org Property',
            address='A1',
            property_type='Apartment',
            organization=self.org,
        )
        self.assertEqual(prop.owner_id, self.owner.id)

    def test_explicit_owner_is_not_overwritten(self):
        other = User.objects.create_user(username='pexplicit', password='pass12345')
        prop = Property.objects.create(
            name='Explicit',
            address='A1',
            property_type='Apartment',
            organization=self.org,
            owner=other,
        )
        self.assertEqual(prop.owner_id, other.id)

    def test_property_without_org_still_works(self):
        prop = Property.objects.create(
            name='Legacy', address='A1', property_type='House', owner=self.owner
        )
        self.assertIsNone(prop.organization_id)
        self.assertEqual(prop.owner_id, self.owner.id)


class AgentRegistrationTests(TestCase):
    def test_agent_track_registration(self):
        from rest_framework.test import APIClient

        client = APIClient()
        response = client.post(
            '/api/register/',
            {
                'username': 'agentreg',
                'email': 'agent@test.com',
                'password': 'strongpass123',
                'first_name': 'Ag',
                'last_name': 'Ent',
                'track': 'agent',
            },
        )
        self.assertEqual(response.status_code, 201)
        org = Organization.objects.get(memberships__user__username='agentreg')
        self.assertEqual(org.track, 'agent')
        self.assertEqual(Subscription.objects.get(organization=org).plan, 'agent_free')

    def test_owner_track_registration(self):
        from rest_framework.test import APIClient

        client = APIClient()
        response = client.post(
            '/api/register/',
            {
                'username': 'ownerreg',
                'email': 'owner@test.com',
                'password': 'strongpass123',
                'track': 'owner',
            },
        )
        self.assertEqual(response.status_code, 201)
        org = Organization.objects.get(memberships__user__username='ownerreg')
        self.assertEqual(org.track, 'owner')

    def test_registration_defaults_to_owner(self):
        from rest_framework.test import APIClient

        client = APIClient()
        response = client.post(
            '/api/register/',
            {'username': 'defaultreg', 'password': 'strongpass123'},
        )
        self.assertEqual(response.status_code, 201)
        org = Organization.objects.get(memberships__user__username='defaultreg')
        self.assertEqual(org.track, 'owner')

    def test_invalid_track_rejected(self):
        from rest_framework.test import APIClient

        client = APIClient()
        response = client.post(
            '/api/register/',
            {'username': 'badtrack', 'password': 'strongpass123', 'track': 'admin'},
        )
        self.assertEqual(response.status_code, 400)

    def test_agent_track_not_set_on_user(self):
        from rest_framework.test import APIClient

        client = APIClient()
        response = client.post(
            '/api/register/',
            {
                'username': 'trackleak',
                'password': 'strongpass123',
                'track': 'agent',
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertNotIn('track', response.data)


class ScopeTests(TestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(username='suser1', password='pass12345')
        self.other_user = User.objects.create_user(username='suser2', password='pass12345')
        self.org1 = Organization.objects.get(memberships__user=self.client_user)
        self.org2 = Organization.objects.get(memberships__user=self.other_user)
        self.prop1 = Property.objects.create(
            name='Scoped 1', address='A1', property_type='Apartment', organization=self.org1
        )
        self.prop2 = Property.objects.create(
            name='Scoped 2', address='A2', property_type='House', organization=self.org2
        )

    def test_organizations_for_returns_own(self):
        from workspaces.scopes import organizations_for

        self.assertEqual(list(organizations_for(self.client_user)), [self.org1])

    def test_accessible_properties_is_scoped(self):
        from workspaces.scopes import accessible_properties

        names = list(accessible_properties(self.client_user).values_list('name', flat=True))
        self.assertEqual(names, ['Scoped 1'])

    def test_can_access_own_and_not_others(self):
        from workspaces.scopes import can_access_property

        self.assertTrue(can_access_property(self.client_user, self.prop1))
        self.assertFalse(can_access_property(self.client_user, self.prop2))

    def test_unaccepted_membership_denies_access(self):
        from workspaces.scopes import accessible_properties

        OrganizationMembership.objects.filter(
            organization=self.org2, user=self.other_user
        ).update(accepted_at=None)
        self.assertEqual(accessible_properties(self.other_user).count(), 0)

    def test_property_membership_grants_access(self):
        from workspaces.scopes import can_access_property

        PropertyMembership.objects.create(
            property=self.prop2, user=self.client_user, role='viewer'
        )
        self.assertTrue(can_access_property(self.client_user, self.prop2))


class UnlinkedPropertyTests(TestCase):
    """Legacy rows with no organization must stay reachable during Phase 2."""

    def setUp(self):
        self.user = User.objects.create_user(username='orphanuser', password='pass12345')
        self.other = User.objects.create_user(username='orphanother', password='pass12345')
        self.org = Organization.objects.get(memberships__user=self.user)
        self.linked = Property.objects.create(
            name='Linked', address='A', property_type='Apartment', organization=self.org
        )
        self.orphan = Property.objects.create(
            name='Orphan', address='A', property_type='House', owner=self.user
        )
        self.other_orphan = Property.objects.create(
            name='Other Orphan', address='A', property_type='House', owner=self.other
        )

    def test_orphan_visible_to_its_owner(self):
        from workspaces.scopes import accessible_properties

        names = set(accessible_properties(self.user).values_list('name', flat=True))
        self.assertEqual(names, {'Linked', 'Orphan'})

    def test_other_users_orphan_hidden(self):
        from workspaces.scopes import accessible_properties

        names = set(
            accessible_properties(self.other).values_list('name', flat=True)
        )
        self.assertNotIn('Orphan', names)

    def test_can_access_orphan_only_for_owner(self):
        from workspaces.scopes import can_access_property

        self.assertTrue(can_access_property(self.user, self.orphan))
        self.assertFalse(can_access_property(self.other, self.orphan))

    def test_query_helper_matches_helper(self):
        from workspaces.scopes import accessible_properties, accessible_properties_query

        via_q = Property.objects.filter(
            accessible_properties_query(self.user)
        ).values_list('name', flat=True)
        self.assertEqual(set(via_q), set(accessible_properties(self.user).values_list('name', flat=True)))

    def test_query_helper_with_prefix(self):
        from properties.models import Unit
        from workspaces.scopes import accessible_properties_query

        Unit.objects.create(property=self.linked, unit_number='A1')
        Unit.objects.create(property=self.orphan, unit_number='A2')
        Unit.objects.create(property=self.other_orphan, unit_number='A3')
        numbers = set(
            Unit.objects.filter(accessible_properties_query(self.user, prefix='property__'))
            .values_list('unit_number', flat=True)
        )
        self.assertEqual(numbers, {'A1', 'A2'})

    def test_query_helper_deep_prefix(self):
        from properties.models import Payment, Tenant, Unit
        from workspaces.scopes import accessible_properties_query

        unit = Unit.objects.create(property=self.linked, unit_number='B1')
        tenant = Tenant.objects.create(
            unit=unit, name='Tenant A', annual_rent=100,
        )
        Payment.objects.create(
            tenant=tenant, amount=100, payment_date='2026-01-05',
            payment_method='Cash',
        )
        payments = Payment.objects.filter(
            accessible_properties_query(self.user, prefix='tenant__unit__property__')
        )
        self.assertEqual(payments.count(), 1)
        self.assertEqual(
            Payment.objects.filter(
                accessible_properties_query(self.other, prefix='tenant__unit__property__')
            ).count(),
            0,
        )