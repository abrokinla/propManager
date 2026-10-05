from django.contrib.auth.models import User
from django.test import TestCase

from workspaces.plans import UNLIMITED, get_limit, has_feature, plans_for_track
from workspaces.services.limits import (
    FeatureDisabled,
    PlanLimitExceeded,
    describe,
    enforce,
    enforce_feature,
    usage,
)
from workspaces.services.provisioning import provision_workspace


def sub_for(username, track='owner', plan=None, overrides=None, interval=None):
    user = User.objects.create_user(username=username, password='pass12345')
    org = provision_workspace(user, track=track)
    from workspaces.models import Subscription

    sub = Subscription.objects.get(organization=org)
    if plan:
        sub.plan = plan
    if interval:
        sub.interval = interval
    if overrides is not None:
        sub.limit_overrides = overrides
    sub.save()
    return sub


class PlanDefinitionTests(TestCase):
    def test_all_eight_plans_exist(self):
        from workspaces.plans import PLANS

        self.assertEqual(len(plans_for_track('agent')), 4)
        self.assertEqual(len(plans_for_track('owner')), 4)
        self.assertEqual(len(PLANS), 8)

    def test_starter_price_is_1200_cents(self):
        from workspaces.plans import price_cents

        self.assertEqual(price_cents('agent_starter', 'month'), 1200)
        self.assertEqual(price_cents('agent_starter', 'year'), 12000)

    def test_annual_monthly_equivalent_is_below_monthly(self):
        from workspaces.plans import PLANS

        for key in ('agent_starter', 'agent_pro', 'agent_agency', 'owner_pro'):
            self.assertLess(PLANS[key]['annual_monthly_equivalent'], PLANS[key]['monthly_cents'])

    def test_free_tier_is_one_property_both_tracks(self):
        self.assertEqual(get_limit('agent_free', 'properties'), 1)
        self.assertEqual(get_limit('owner_free', 'properties'), 1)

    def test_whatsapp_api_flagged_pro_and_agency_only(self):
        self.assertFalse(has_feature('agent_free', 'whatsapp_api'))
        self.assertFalse(has_feature('agent_starter', 'whatsapp_api'))
        self.assertTrue(has_feature('agent_pro', 'whatsapp_api'))
        self.assertTrue(has_feature('agent_agency', 'whatsapp_api'))

    def test_whatsapp_api_absent_from_owner_plans(self):
        for plan in plans_for_track('owner'):
            self.assertFalse(has_feature(plan, 'whatsapp_api'))

    def test_owner_tier_progression(self):
        self.assertEqual(get_limit('owner_free', 'units'), 5)
        self.assertEqual(get_limit('owner_starter', 'units'), 30)
        self.assertEqual(get_limit('owner_pro', 'units'), UNLIMITED)


class LimitResolutionTests(TestCase):
    def test_override_wins_over_plan(self):
        self.assertEqual(get_limit('owner_free', 'properties', {'properties': 7}), 7)

    def test_override_zero_is_respected(self):
        self.assertEqual(get_limit('owner_free', 'properties', {'properties': 0}), 0)

    def test_unknown_metric_falls_back_to_none(self):
        self.assertIsNone(get_limit('owner_free', 'not_a_metric'))


class EnforceTests(TestCase):
    def test_allows_below_limit(self):
        sub = sub_for('lim1', plan='owner_free')
        self.assertTrue(enforce(sub, 'properties', 1))
        with self.assertRaises(PlanLimitExceeded):
            enforce(sub, 'properties', 2)

    def test_unlimited_never_raises(self):
        sub = sub_for('lim2', plan='owner_enterprise')
        self.assertTrue(enforce(sub, 'properties', 9999))

    def test_grandfathered_user_can_exceed_free_limit(self):
        sub = sub_for('lim3', plan='owner_free', overrides={'properties': 12})
        self.assertTrue(enforce(sub, 'properties', 12))
        with self.assertRaises(PlanLimitExceeded):
            enforce(sub, 'properties', 13)

    def test_error_payload_shape(self):
        sub = sub_for('lim4', plan='owner_free')
        with self.assertRaises(PlanLimitExceeded) as ctx:
            enforce(sub, 'properties', 2)
        payload = ctx.exception.to_payload()
        self.assertEqual(payload['error'], 'plan_limit_reached')
        self.assertEqual(payload['metric'], 'properties')
        self.assertEqual(payload['current'], 2)
        self.assertEqual(payload['limit'], 1)
        self.assertEqual(payload['upgrade_url'], '/pricing')

    def test_usage_returns_tuple(self):
        sub = sub_for('lim5', plan='owner_free')
        allowed, limit = usage(sub, 'properties', 1)
        self.assertTrue(allowed)
        self.assertEqual(limit, 1)

    def test_tenant_limit_enforced(self):
        sub = sub_for('lim6', plan='owner_free')
        self.assertTrue(enforce(sub, 'active_tenants', 3))
        with self.assertRaises(PlanLimitExceeded):
            enforce(sub, 'active_tenants', 4)

    def test_ai_limit_enforced(self):
        sub = sub_for('lim7', plan='agent_free')
        self.assertTrue(enforce(sub, 'ai_monthly', 5))
        with self.assertRaises(PlanLimitExceeded):
            enforce(sub, 'ai_monthly', 6)

    def test_ai_unlimited_on_agency(self):
        sub = sub_for('lim8', track='agent', plan='agent_agency')
        self.assertTrue(enforce(sub, 'ai_monthly', 10_000))


class FeatureGateTests(TestCase):
    def test_disabled_feature_raises(self):
        sub = sub_for('feat1', track='agent', plan='agent_starter')
        with self.assertRaises(FeatureDisabled) as ctx:
            enforce_feature(sub, 'whatsapp_api')
        self.assertEqual(ctx.exception.to_payload()['feature'], 'whatsapp_api')

    def test_enabled_feature_passes(self):
        sub = sub_for('feat2', track='agent', plan='agent_pro')
        self.assertTrue(enforce_feature(sub, 'whatsapp_api'))

    def test_esign_gated_on_owner_plans(self):
        sub = sub_for('feat3', plan='owner_free')
        with self.assertRaises(FeatureDisabled):
            enforce_feature(sub, 'esign')
        sub2 = sub_for('feat4', plan='owner_starter')
        self.assertTrue(enforce_feature(sub2, 'esign'))


class DescribeTests(TestCase):
    def test_describe_returns_resolved_limits(self):
        sub = sub_for('desc1', plan='owner_free', overrides={'properties': 5})
        result = describe(sub)
        self.assertEqual(result['plan'], 'owner_free')
        self.assertEqual(result['label'], 'Free')
        self.assertEqual(result['limits']['properties'], 5)
        self.assertEqual(result['monthly_cents'], 0)

    def test_describe_paid_plan(self):
        sub = sub_for('desc2', plan='agent_pro', interval='year')
        result = describe(sub)
        self.assertEqual(result['interval'], 'year')
        self.assertEqual(result['monthly_cents'], 2900)
        self.assertEqual(result['annual_price_cents'], 29000)
        self.assertTrue(result['features']['whatsapp_api'])