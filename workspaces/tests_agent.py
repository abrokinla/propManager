"""Phase 5: agent CRM endpoints and KYC gating."""
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from properties.models import Property, PropertyView, VisitBooking
from workspaces.models import AgentKYC, Organization
from workspaces.services.provisioning import provision_workspace


def make_agent(username='agentu', verified=False):
    user = User.objects.create_user(
        username=username, password='pass12345', first_name='Ada', last_name='A'
    )
    org = provision_workspace(user, track='agent')
    kyc = AgentKYC.objects.get(user=user)
    if verified:
        kyc.status = 'verified'
        kyc.license_number = 'LIC-123'
        kyc.save()
    return user, org, kyc


class AgentRegistrationTests(TestCase):
    def test_agent_track_org_created_on_register(self):
        client = APIClient()
        response = client.post(
            '/api/register/',
            {
                'username': 'newagent',
                'password': 'strongpass123',
                'track': 'agent',
            },
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        org = Organization.objects.get(memberships__user__username='newagent')
        self.assertEqual(org.track, 'agent')

    def test_agent_has_slug_and_kyc_record(self):
        user, org, kyc = make_agent()
        self.assertEqual(kyc.status, 'unsubmitted')
        self.assertEqual(len(user.profile.agent_public_slug), 12)
        self.assertNotEqual(
            user.profile.agent_public_slug, user.profile.public_slug
        )

    def test_slugs_are_unique_across_users(self):
        u1, _, _ = make_agent('a1')
        u2, _, _ = make_agent('a2')
        self.assertNotEqual(
            u1.profile.agent_public_slug, u2.profile.agent_public_slug
        )


class AgentProfileEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user, self.org, _ = make_agent()
        self.client.force_authenticate(user=self.user)

    def test_get_profile(self):
        response = self.client.get('/api/agent/profile/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['track'] if 'track' in response.data else 'agent', 'agent')
        self.assertFalse(response.data['verified'])
        self.assertEqual(response.data['kyc_status'], 'unsubmitted')

    def test_update_profile_bio_and_whatsapp(self):
        response = self.client.put(
            '/api/agent/profile/',
            {'bio': 'Top agent in Lagos', 'whatsapp': '+2348000000000'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.org.refresh_from_db()
        self.assertEqual(self.org.bio, 'Top agent in Lagos')

    def test_owner_track_user_gets_404(self):
        owner = User.objects.create_user(username='plainowner', password='pass12345')
        self.client.force_authenticate(user=owner)
        response = self.client.get('/api/agent/profile/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_rejected(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(
            self.client.get('/api/agent/profile/').status_code,
            status.HTTP_401_UNAUTHORIZED,
        )


class AgentKYCTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user, self.org, self.kyc = make_agent()
        self.client.force_authenticate(user=self.user)

    def test_get_status_defaults_unsubmitted(self):
        response = self.client.get('/api/agent/kyc/submit/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'unsubmitted')

    def test_submit_sets_pending(self):
        response = self.client.post(
            '/api/agent/kyc/submit/',
            {'license_number': 'LIC-999', 'documents': {'id': 'https://x/id.png'}},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.kyc.refresh_from_db()
        self.assertEqual(self.kyc.status, 'pending')
        self.assertEqual(self.kyc.license_number, 'LIC-999')

    def test_status_is_read_only(self):
        self.client.post('/api/agent/kyc/submit/', {'license_number': 'L1'})
        response = self.client.post(
            '/api/agent/kyc/submit/', {'status': 'verified', 'license_number': 'L2'}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.kyc.refresh_from_db()
        self.assertEqual(self.kyc.status, 'pending')

    def test_double_submit_rejected(self):
        self.client.post('/api/agent/kyc/submit/', {'license_number': 'L1'})
        response = self.client.post('/api/agent/kyc/submit/', {'license_number': 'L2'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verified_agent_cannot_resubmit(self):
        self.kyc.status = 'verified'
        self.kyc.save()
        response = self.client.post('/api/agent/kyc/submit/', {'license_number': 'X'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejected_agent_may_resubmit(self):
        self.kyc.status = 'rejected'
        self.kyc.rejection_reason = 'Blurry ID'
        self.kyc.save()
        response = self.client.post(
            '/api/agent/kyc/submit/', {'license_number': 'L3'}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.kyc.refresh_from_db()
        self.assertEqual(self.kyc.status, 'pending')
        self.assertEqual(self.kyc.rejection_reason, '')


class PublicAgentProfileTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user, self.org, self.kyc = make_agent(verified=True)
        self.slug = self.user.profile.agent_public_slug
        self.prop = Property.objects.create(
            name='Agent Listing',
            address='Lagos, Nigeria',
            property_type='Apartment',
            organization=self.org,
            is_published=True,
        )
        Property.objects.create(
            name='Draft',
            address='Lagos',
            property_type='Studio',
            organization=self.org,
            is_published=False,
        )

    def test_public_profile_visible_without_auth(self):
        response = self.client.get(f'/api/public/agents/{self.slug}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['verified'])
        self.assertEqual(response.data['first_name'], 'Ada')

    def test_public_profile_404_when_unverified(self):
        self.kyc.status = 'pending'
        self.kyc.save()
        response = self.client.get(f'/api/public/agents/{self.slug}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_public_properties_only_published(self):
        response = self.client.get(f'/api/public/agents/{self.slug}/properties/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [p['name'] for p in response.data]
        self.assertEqual(names, ['Agent Listing'])

    def test_public_profile_counts_published_properties(self):
        response = self.client.get(f'/api/public/agents/{self.slug}/')
        self.assertEqual(response.data['property_count'], 1)

    def test_unknown_slug_404(self):
        self.assertEqual(
            self.client.get('/api/public/agents/nope12345678/').status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_owner_slug_does_not_resolve_agent_profile(self):
        # public_slug is a separate namespace from agent_public_slug
        response = self.client.get(f'/api/public/agents/{self.user.profile.public_slug}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class AgentLeadsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user, self.org, _ = make_agent(verified=True)
        self.client.force_authenticate(user=self.user)
        self.prop = Property.objects.create(
            name='Lead Prop', address='A', property_type='House', organization=self.org
        )
        other_org = provision_workspace(
            User.objects.create_user(username='rival', password='pass12345'),
            track='agent',
        )
        self.rival_prop = Property.objects.create(
            name='Rival Prop', address='B', property_type='House', organization=other_org
        )

    def test_leads_scoped_to_own_properties(self):
        VisitBooking.objects.create(
            property=self.prop,
            guest_name='Mine',
            guest_email='mine@test.com',
            visit_date='2026-01-20',
            visit_time='10:00',
        )
        VisitBooking.objects.create(
            property=self.rival_prop,
            guest_name='Theirs',
            guest_email='theirs@test.com',
            visit_date='2026-01-20',
            visit_time='10:00',
        )
        response = self.client.get('/api/agent/leads/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [b['guest_name'] for b in response.data['bookings']]
        self.assertEqual(names, ['Mine'])

    def test_leads_include_view_counts(self):
        PropertyView.objects.create(property=self.prop)
        PropertyView.objects.create(property=self.prop)
        PropertyView.objects.create(property=self.rival_prop)
        response = self.client.get('/api/agent/leads/')
        self.assertEqual(response.data['view_count'], 2)

    def test_stats_shape(self):
        VisitBooking.objects.create(
            property=self.prop,
            guest_name='A',
            guest_email='a@test.com',
            visit_date='2026-01-20',
            visit_time='10:00',
            status='pending',
        )
        response = self.client.get('/api/agent/stats/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_properties'], 1)
        self.assertEqual(response.data['booking_count'], 1)
        self.assertEqual(response.data['pending_bookings'], 1)

    def test_stats_requires_auth(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(
            self.client.get('/api/agent/stats/').status_code,
            status.HTTP_401_UNAUTHORIZED,
        )


class KYCGatingTests(TestCase):
    """Unverified agents are capped at one property."""

    def setUp(self):
        self.client = APIClient()
        self.user, self.org, self.kyc = make_agent()
        self.client.force_authenticate(user=self.user)

    def test_pending_agent_property_limit_is_one(self):
        response = self.client.get('/api/agent/stats/')
        self.assertEqual(response.data['property_limit'], 1)

    def test_verified_agent_limit_follows_plan(self):
        self.kyc.status = 'verified'
        self.kyc.save()
        response = self.client.get('/api/agent/stats/')
        # free plan allows one property too
        self.assertEqual(response.data['property_limit'], 1)

    def test_pro_plan_raises_verified_limit(self):
        self.kyc.status = 'verified'
        self.kyc.save()
        self.org.subscription.plan = 'agent_pro'
        self.org.subscription.save()
        response = self.client.get('/api/agent/stats/')
        self.assertEqual(response.data['property_limit'], 20)

    def test_pending_agent_capped_even_on_paid_plan(self):
        self.org.subscription.plan = 'agent_pro'
        self.org.subscription.save()
        response = self.client.get('/api/agent/stats/')
        self.assertEqual(response.data['property_limit'], 1)