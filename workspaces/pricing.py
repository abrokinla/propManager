"""Public plan catalog for the pricing page.

Numbers and facts only. Marketing copy stays in the frontend message files so
it can be localized; this endpoint never returns a sentence.

Two deliberate omissions:

- ``annual_monthly_equivalent`` is not exposed. It is the internally derived
  (and cheaper) per-month figure; the card shows the monthly price and states
  the annual total separately, so shipping it would invite the frontend to
  advertise a discount nobody priced.
"""
from django.conf import settings
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from workspaces.plans import PLANS, plans_for_track

#: Features advertised on cards but not actually purchasable yet. WhatsApp
#: Business API is gated behind Meta approval, which has not been granted.
PENDING_FEATURES = {'whatsapp_api'}

#: The tier we mark "most popular" per track. Matches the card highlight the
#: old hardcoded pricing section used.
POPULAR_PLAN = {'agent': 'agent_pro', 'owner': 'owner_pro'}

#: Map internal plan key -> Paddle price IDs (from env). Populated when
#: Paddle env vars are set. Only paid plans have IDs.
PADDLE_PRICE_MAP = {
    'agent_starter': {
        'monthly': getattr(settings, 'PADDLE_PRICE_AGENT_STARTER_MONTHLY', ''),
        'annual': getattr(settings, 'PADDLE_PRICE_AGENT_STARTER_ANNUAL', ''),
    },
    'agent_pro': {
        'monthly': getattr(settings, 'PADDLE_PRICE_AGENT_PRO_MONTHLY', ''),
        'annual': getattr(settings, 'PADDLE_PRICE_AGENT_PRO_ANNUAL', ''),
    },
    'agent_agency': {
        'monthly': getattr(settings, 'PADDLE_PRICE_AGENT_AGENCY_MONTHLY', ''),
        'annual': getattr(settings, 'PADDLE_PRICE_AGENT_AGENCY_ANNUAL', ''),
    },
    'owner_starter': {
        'monthly': getattr(settings, 'PADDLE_PRICE_OWNER_STARTER_MONTHLY', ''),
        'annual': getattr(settings, 'PADDLE_PRICE_OWNER_STARTER_ANNUAL', ''),
    },
    'owner_pro': {
        'monthly': getattr(settings, 'PADDLE_PRICE_OWNER_PRO_MONTHLY', ''),
        'annual': getattr(settings, 'PADDLE_PRICE_OWNER_PRO_ANNUAL', ''),
    },
    'owner_enterprise': {
        'monthly': getattr(settings, 'PADDLE_PRICE_OWNER_ENTERPRISE_MONTHLY', ''),
        'annual': getattr(settings, 'PADDLE_PRICE_OWNER_ENTERPRISE_ANNUAL', ''),
    },
}

UNLIMITED = -1


def _has_paddle_prices() -> bool:
    """Return True if at least one paid plan has both monthly and annual Paddle IDs."""
    for plan_key, ids in PADDLE_PRICE_MAP.items():
        if ids['monthly'] and ids['annual']:
            return True
    return False


def _limit_for_display(value):
    """-1 becomes None so the frontend does not have to special-case -1."""
    return None if value == UNLIMITED else value


def serialize_plan(plan_key):
    plan = PLANS[plan_key]
    paddle_ids = PADDLE_PRICE_MAP.get(plan_key, {'monthly': '', 'annual': ''})
    return {
        'key': plan_key,
        'label': plan['label'],
        'track': plan_key.split('_', 1)[0],
        'monthly_cents': plan['monthly_cents'],
        'annual_cents': plan['annual_price_cents'],
        'display_monthly_cents': plan['monthly_cents'],
        'is_free': plan['monthly_cents'] == 0,
        'limits': {
            metric: _limit_for_display(value)
            for metric, value in plan['limits'].items()
        },
        'features': {
            name: enabled for name, enabled in plan['features'].items()
        },
        'pending_features': sorted(
            name for name in plan['features']
            if plan['features'][name] and name in PENDING_FEATURES
        ),
        'has_pending_features': any(
            plan['features'][name] and name in PENDING_FEATURES
            for name in plan['features']
        ),
        'paddle_price_id_monthly': paddle_ids['monthly'],
        'paddle_price_id_annual': paddle_ids['annual'],
    }


class PricingView(APIView):
    """GET /api/pricing/ - the full catalog, both tracks."""

    permission_classes = [AllowAny]

    def get(self, request):
        tracks = {}
        for track in ('agent', 'owner'):
            keys = plans_for_track(track)
            tracks[track] = {
                'label': 'Agent' if track == 'agent' else 'Owner',
                'plans': [serialize_plan(key) for key in keys],
                'popular_plan': POPULAR_PLAN[track],
            }
        return Response({
            'currency': 'USD',
            'whatsapp_api_available': False,
            'checkout_available': _has_paddle_prices(),
            'tracks': tracks,
        })