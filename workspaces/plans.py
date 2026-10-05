"""Plan definitions and limit resolution for PropManager.

Prices are stored in USD cents. ``annual_price_cents`` is the total charged once
per year; ``annual_monthly_equivalent`` is what we advertise as the per-month
price on the annual billing cycle.

``-1`` means unlimited.
"""

UNLIMITED = -1

# Metric keys used by workspaces.services.limits.enforce()
PROPERTIES = 'properties'
UNITS = 'units'
ACTIVE_TENANTS = 'active_tenants'
TEAM_MEMBERS = 'team_members'
AI_MONTHLY = 'ai_monthly'
ANALYTICS_DAYS = 'analytics_days'
STORAGE_MB = 'storage_mb'
LEADS = 'leads'

AGENT_PLANS = {
    'agent_free': {
        'label': 'Free',
        'monthly_cents': 0,
        'annual_price_cents': 0,
        'limits': {
            PROPERTIES: 1,
            TEAM_MEMBERS: 1,
            ANALYTICS_DAYS: 30,
            AI_MONTHLY: 5,
            LEADS: UNLIMITED,
            STORAGE_MB: 100,
        },
        'features': {
            'lead_export': False,
            'custom_domain': False,
            'whatsapp_api': False,
            'white_label': False,
        },
    },
    'agent_starter': {
        'label': 'Starter',
        'monthly_cents': 1200,
        'annual_price_cents': 12000,
        'limits': {
            PROPERTIES: 5,
            TEAM_MEMBERS: 3,
            ANALYTICS_DAYS: 365,
            AI_MONTHLY: 50,
            LEADS: UNLIMITED,
            STORAGE_MB: 500,
        },
        'features': {
            'lead_export': True,
            'custom_domain': False,
            'whatsapp_api': False,
            'white_label': False,
        },
    },
    'agent_pro': {
        'label': 'Pro',
        'monthly_cents': 2900,
        'annual_price_cents': 29000,
        'limits': {
            PROPERTIES: 20,
            TEAM_MEMBERS: 10,
            ANALYTICS_DAYS: 1095,
            AI_MONTHLY: UNLIMITED,
            LEADS: UNLIMITED,
            STORAGE_MB: 2000,
        },
        'features': {
            'lead_export': True,
            'custom_domain': True,
            'whatsapp_api': True,
            'white_label': False,
        },
    },
    'agent_agency': {
        'label': 'Agency',
        'monthly_cents': 7900,
        'annual_price_cents': 79000,
        'limits': {
            PROPERTIES: UNLIMITED,
            TEAM_MEMBERS: UNLIMITED,
            ANALYTICS_DAYS: UNLIMITED,
            AI_MONTHLY: UNLIMITED,
            LEADS: UNLIMITED,
            STORAGE_MB: UNLIMITED,
        },
        'features': {
            'lead_export': True,
            'custom_domain': True,
            'whatsapp_api': True,
            'white_label': True,
        },
    },
}

OWNER_PLANS = {
    'owner_free': {
        'label': 'Free',
        'monthly_cents': 0,
        'annual_price_cents': 0,
        'limits': {
            PROPERTIES: 1,
            UNITS: 5,
            ACTIVE_TENANTS: 3,
            TEAM_MEMBERS: 1,
            STORAGE_MB: 100,
        },
        'features': {
            'esign': False,
            'compliance': False,
            'api': False,
        },
    },
    'owner_starter': {
        'label': 'Starter',
        'monthly_cents': 2400,
        'annual_price_cents': 24000,
        'limits': {
            PROPERTIES: 5,
            UNITS: 30,
            ACTIVE_TENANTS: 30,
            TEAM_MEMBERS: 3,
            STORAGE_MB: 5000,
        },
        'features': {
            'esign': True,
            'compliance': False,
            'api': False,
        },
    },
    'owner_pro': {
        'label': 'Pro',
        'monthly_cents': 5900,
        'annual_price_cents': 59000,
        'limits': {
            PROPERTIES: 25,
            UNITS: UNLIMITED,
            ACTIVE_TENANTS: UNLIMITED,
            TEAM_MEMBERS: 10,
            STORAGE_MB: 50000,
        },
        'features': {
            'esign': True,
            'compliance': True,
            'api': False,
        },
    },
    'owner_enterprise': {
        'label': 'Enterprise',
        'monthly_cents': 14900,
        'annual_price_cents': 149000,
        'limits': {
            PROPERTIES: UNLIMITED,
            UNITS: UNLIMITED,
            ACTIVE_TENANTS: UNLIMITED,
            TEAM_MEMBERS: UNLIMITED,
            STORAGE_MB: UNLIMITED,
        },
        'features': {
            'esign': True,
            'compliance': True,
            'api': True,
        },
    },
}

PLANS = {**AGENT_PLANS, **OWNER_PLANS}


def _derive_annual_equivalents(plans):
    """Advertised per-month price on the annual cycle = annual total / 12.

    Derived rather than hand-written. The old hand-maintained field had
    agent_starter at 1000 ($10/mo) against a $12/mo monthly price, which
    quietly invented a two-months-free discount nobody approved. The annual
    total stays the source of truth; this is presentation only.
    """
    for plan in plans.values():
        plan['annual_monthly_equivalent'] = round(
            plan['annual_price_cents'] / 12
        )


_derive_annual_equivalents(PLANS)

TRACK_PLAN_ORDER = {
    'agent': ['agent_free', 'agent_starter', 'agent_pro', 'agent_agency'],
    'owner': [
        'owner_free',
        'owner_starter',
        'owner_pro',
        'owner_enterprise',
    ],
}


def plans_for_track(track):
    return TRACK_PLAN_ORDER.get(track, TRACK_PLAN_ORDER['owner'])


def get_plan(plan_key):
    return PLANS.get(plan_key, PLANS['owner_free'])


def get_limit(plan_key, metric, overrides=None):
    """Resolve a limit, honouring limit_overrides first.

    ``limit_overrides`` is used for grandfathering existing users onto the free
    tier while keeping their current property count, and doubles as a support
    lever ("I bumped your limit").
    """
    if overrides and metric in overrides:
        return overrides[metric]
    return get_plan(plan_key)['limits'].get(metric)


def has_feature(plan_key, feature):
    return bool(get_plan(plan_key)['features'].get(feature, False))


def price_cents(plan_key, interval='month'):
    """Total charged for one billing cycle."""
    plan = get_plan(plan_key)
    return plan['annual_price_cents'] if interval == 'year' else plan['monthly_cents']


def display_price_cents(plan_key, interval='month'):
    """Price to show on the pricing card.

    Always the monthly price, on both cycles: the annual card reads
    "$12/month, billed annually" and states the $120 total separately. The
    cheaper annual_monthly_equivalent stays an internal figure so nobody
    implies a discount that was never priced.
    """
    return get_plan(plan_key)['monthly_cents']