"""Phase 7 backend: public pricing catalog, KYC review, dashboard track fields.

The pricing endpoint is what the pricing page renders from. It exists because
the page used to carry its own hardcoded Naira and USD price objects that
disagreed with PLANS, so a visitor could pick a plan that did not exist.
"""
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from properties.models import Property
from workspaces.models import AgentKYC
from workspaces.plans import PLANS, plans_for_track
from workspaces.services.provisioning import add_member, provision_workspace


def make_agent(username='pricingagent', verified=True):
    user = User.objects.create_user(
        username=username, password='pass12345', first_name='Priya'
    )
    org = provision_workspace(user, track='agent')
    kyc = AgentKYC.objects.get(user=user)
    if verified:
        kyc.status = 'verified'
        kyc.save()
    return user, org, kyc


class PricingCatalogTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.response = self.client.get('/api/pricing/')
        self.data = self.response.data

    def test_endpoint_is_public(self):
        self.assertEqual(self.response.status_code, status.HTTP_200_OK)

    def test_both_tracks_present(self):
        self.assertEqual(set(self.data['tracks']), {'agent', 'owner'})

    def test_track_plan_counts(self):
        self.assertEqual(len(self.data['tracks']['agent']['plans']), 4)
        self.assertEqual(len(self.data['tracks']['owner']['plans']), 4)

    def test_plan_keys_match_plan_order(self):
        agent_keys = [p['key'] for p in self.data['tracks']['agent']['plans']]
        self.assertEqual(agent_keys, plans_for_track('agent'))
        owner_keys = [p['key'] for p in self.data['tracks']['owner']['plans']]
        self.assertEqual(owner_keys, plans_for_track('owner'))

    def test_every_catalog_plan_exists_in_plans(self):
        for track in ('agent', 'owner'):
            for plan in self.data['tracks'][track]['plans']:
                self.assertIn(plan['key'], PLANS)

    def test_prices_match_plans(self):
        for track in ('agent', 'owner'):
            for plan in self.data['tracks'][track]['plans']:
                source = PLANS[plan['key']]
                self.assertEqual(plan['monthly_cents'], source['monthly_cents'])
                self.assertEqual(plan['annual_cents'], source['annual_price_cents'])

    def test_locked_price_points(self):
        wanted = {
            'agent_free': (0, 0),
            'agent_starter': (1200, 12000),
            'agent_pro': (2900, 29000),
            'agent_agency': (7900, 79000),
            'owner_free': (0, 0),
            'owner_starter': (2400, 24000),
            'owner_pro': (5900, 59000),
            'owner_enterprise': (14900, 149000),
        }
        seen = {}
        for track in ('agent', 'owner'):
            for plan in self.data['tracks'][track]['plans']:
                seen[plan['key']] = (plan['monthly_cents'], plan['annual_cents'])
        self.assertEqual(seen, wanted)

    def test_display_price_is_monthly_on_both_cycles(self):
        for track in ('agent', 'owner'):
            for plan in self.data['tracks'][track]['plans']:
                self.assertEqual(plan['display_monthly_cents'], plan['monthly_cents'])

    def test_annual_equivalent_is_never_exposed(self):
        """Shipping the derived per-month figure invites a phantom discount."""
        raw = self.client.get('/api/pricing/').content.decode()
        self.assertNotIn('annual_monthly_equivalent', raw)

    def test_starter_does_not_advertise_the_ten_dollar_figure(self):
        agent = {
            p['key']: p for p in self.data['tracks']['agent']['plans']
        }
        # The drift that shipped: agent_starter at $10/mo against a $12 price.
        self.assertEqual(agent['agent_starter']['display_monthly_cents'], 1200)
        self.assertEqual(agent['agent_starter']['annual_cents'], 12000)

    def test_unlimited_limits_are_null_not_minus_one(self):
        agency = [
            p for p in self.data['tracks']['agent']['plans']
            if p['key'] == 'agent_agency'
        ][0]
        # Agency is unlimited across the board; -1 must not leak to the client.
        self.assertIsNone(agency['limits']['properties'])
        self.assertIsNone(agency['limits']['team_members'])
        self.assertIsNone(agency['limits']['ai_monthly'])
        self.assertNotIn(-1, agency['limits'].values())

    def test_free_tier_limits(self):
        free = [p for p in self.data['tracks']['owner']['plans'] if p['key'] == 'owner_free'][0]
        self.assertEqual(free['limits']['properties'], 1)
        self.assertTrue(free['is_free'])

    def test_whatsapp_marked_pending_not_available(self):
        self.assertFalse(self.data['whatsapp_api_available'])
        agent = {
            p['key']: p for p in self.data['tracks']['agent']['plans']
        }
        self.assertEqual(
            agent['agent_pro']['pending_features'], ['whatsapp_api']
        )
        self.assertTrue(agent['agent_pro']['has_pending_features'])
        self.assertFalse(agent['agent_free']['has_pending_features'])

    def test_checkout_flagged_unavailable(self):
        self.assertFalse(self.data['checkout_available'])

    def test_paddle_ids_not_leaked(self):
        raw = self.client.get('/api/pricing/').content.decode()
        self.assertNotIn('paddle', raw.lower())

    def test_currency_is_usd(self):
        self.assertEqual(self.data['currency'], 'USD')

    def test_popular_plan_is_flagged_per_track(self):
        self.assertEqual(self.data['tracks']['agent']['popular_plan'], 'agent_pro')
        self.assertEqual(self.data['tracks']['owner']['popular_plan'], 'owner_pro')

    def test_no_agent_or_nigeria_tier_names(self):
        """The retired page used free/growth/premium and Naira amounts."""
        raw = self.client.get('/api/pricing/').content.decode()
        for stale in ('growth', 'premium', 'NGN', '₦'):
            self.assertNotIn(stale, raw)


class DashboardTrackFieldTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_owner_stats_report_owner_track(self):
        user = User.objects.create_user(username='downer', password='pass12345')
        self.client.force_authenticate(user=user)
        data = self.client.get('/api/dashboard/stats/').data
        self.assertEqual(data['track'], 'owner')

    def test_agent_stats_report_agent_track_and_slug(self):
        user, org, kyc = make_agent('dagent')
        self.client.force_authenticate(user=user)
        data = self.client.get('/api/dashboard/stats/').data
        self.assertEqual(data['track'], 'agent')
        self.assertEqual(data['kyc_status'], 'verified')
        self.assertEqual(
            data['agent_public_slug'], user.profile.agent_public_slug
        )

    def test_agent_slug_differs_from_public_slug(self):
        user, org, kyc = make_agent('dagent2')
        self.client.force_authenticate(user=user)
        data = self.client.get('/api/dashboard/stats/').data
        self.assertNotEqual(data['agent_public_slug'], data['public_slug'])

    def test_kyc_status_reflects_state(self):
        user = User.objects.create_user(username='dagent3', password='pass12345')
        provision_workspace(user, track='agent')
        self.client.force_authenticate(user=user)
        self.assertEqual(
            self.client.get('/api/dashboard/stats/').data['kyc_status'],
            'unsubmitted',
        )
        AgentKYC.objects.filter(user=user).update(status='pending')
        self.assertEqual(
            self.client.get('/api/dashboard/stats/').data['kyc_status'],
            'pending',
        )


class AgentKYCReviewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.reviewer, self.org, _ = make_agent('kycreviewer', verified=True)
        self.applicant = User.objects.create_user(
            username='kycapplicant', password='pass12345'
        )
        provision_workspace(self.applicant, track='agent')
        add_member(self.org, self.applicant, role='staff', accept=True)
        self.kyc = AgentKYC.objects.get(user=self.applicant)
        self.kyc.status = 'pending'
        self.kyc.license_number = 'LIC-77'
        self.kyc.save()
        self.client.force_authenticate(user=self.reviewer)

    def post(self, **extra):
        payload = {'agent_id': self.applicant.id, **extra}
        return self.client.post('/api/agent/kyc/review/', payload)

    def test_owner_can_verify(self):
        response = self.post(decision='verified')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.kyc.refresh_from_db()
        self.assertEqual(self.kyc.status, 'verified')
        self.assertEqual(self.kyc.reviewed_by_id, self.reviewer.id)
        self.assertIsNotNone(self.kyc.reviewed_at)

    def test_owner_can_reject_with_reason(self):
        response = self.post(decision='rejected', reason='Blurry ID photo')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.kyc.refresh_from_db()
        self.assertEqual(self.kyc.status, 'rejected')
        self.assertEqual(self.kyc.rejection_reason, 'Blurry ID photo')

    def test_rejection_requires_reason(self):
        response = self.post(decision='rejected')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.kyc.refresh_from_db()
        self.assertEqual(self.kyc.status, 'pending')

    def test_bad_decision_rejected(self):
        self.assertEqual(
            self.post(decision='maybe').status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_missing_agent_id_rejected(self):
        self.assertEqual(
            self.client.post('/api/agent/kyc/review/', {'decision': 'verified'})
            .status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_cannot_review_self(self):
        self.assertEqual(
            self.post(decision='verified', agent_id=self.reviewer.id).status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_non_member_cannot_be_reviewed(self):
        outsider = User.objects.create_user(username='kycout', password='pass12345')
        provision_workspace(outsider, track='agent')
        response = self.post(decision='verified', agent_id=outsider.id)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_staff_cannot_review(self):
        staff = User.objects.create_user(username='kycstaff', password='pass12345')
        provision_workspace(staff, track='agent')
        add_member(self.org, staff, role='staff', accept=True)
        self.client.force_authenticate(user=staff)
        response = self.client.post(
            '/api/agent/kyc/review/',
            {'agent_id': self.applicant.id, 'decision': 'verified'},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.kyc.refresh_from_db()
        self.assertEqual(self.kyc.status, 'pending')

    def test_viewer_cannot_review(self):
        viewer = User.objects.create_user(username='kycviewer', password='pass12345')
        provision_workspace(viewer, track='agent')
        add_member(self.org, viewer, role='viewer', accept=True)
        self.client.force_authenticate(user=viewer)
        response = self.client.post(
            '/api/agent/kyc/review/',
            {'agent_id': self.applicant.id, 'decision': 'verified'},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_workspace_admin_can_review(self):
        deputy = User.objects.create_user(username='kycdeputy', password='pass12345')
        provision_workspace(deputy, track='agent')
        add_member(self.org, deputy, role='admin', accept=True)
        self.client.force_authenticate(user=deputy)
        response = self.client.post(
            '/api/agent/kyc/review/',
            {'agent_id': self.applicant.id, 'decision': 'verified'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.kyc.refresh_from_db()
        self.assertEqual(self.kyc.status, 'verified')

    def test_reviewer_cannot_touch_a_different_workspace(self):
        other, other_org, _ = make_agent('kycother')
        other_member = User.objects.create_user(username='kycout2', password='pass12345')
        provision_workspace(other_member, track='agent')
        add_member(other_org, other_member, role='staff', accept=True)
        AgentKYC.objects.filter(user=other_member).update(status='pending')
        response = self.post(decision='verified', agent_id=other_member.id)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_owner_track_user_cannot_review(self):
        plain = User.objects.create_user(username='kycplain', password='pass12345')
        self.client.force_authenticate(user=plain)
        # 403, not 404: the caller is authenticated and the request is
        # understood, they simply administer no agent workspace.
        self.assertEqual(
            self.post(decision='verified').status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_requires_auth(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(
            self.post(decision='verified').status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_already_reviewed_cannot_review_again(self):
        self.post(decision='verified')
        response = self.post(decision='rejected', reason='changed my mind')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.kyc.refresh_from_db()
        self.assertEqual(self.kyc.status, 'verified')

    def test_verified_agent_gets_public_profile(self):
        self.post(decision='verified')
        slug = self.applicant.profile.agent_public_slug
        response = self.client.get(f'/api/public/agents/{slug}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_rejected_agent_has_no_public_profile(self):
        self.post(decision='rejected', reason='Expired licence')
        slug = self.applicant.profile.agent_public_slug
        self.assertEqual(
            self.client.get(f'/api/public/agents/{slug}/').status_code,
            status.HTTP_404_NOT_FOUND,
        )


class RetiredAgentEndpointTests(TestCase):
    def test_old_public_agent_endpoint_is_gone(self):
        """public/properties/agent/<slug>/ used the wrong slug namespace."""
        client = APIClient()
        user, org, kyc = make_agent('retired')
        self.assertEqual(
            client.get(
                f'/api/public/properties/agent/{user.profile.public_slug}/'
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_new_agent_endpoint_is_live(self):
        client = APIClient()
        user, org, kyc = make_agent('retired2')
        Property.objects.create(
            name='Listed', address='Lagos', property_type='House',
            organization=org, is_published=True,
        )
        response = client.get(f'/api/public/agents/{user.profile.agent_public_slug}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)