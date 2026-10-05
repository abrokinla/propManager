"""Plan limit enforcement.

``enforce()`` raises ``PlanLimitExceeded`` which the API layer converts to an
HTTP 402 with an upgrade payload. Limits resolve in this order:

1. ``Subscription.limit_overrides[metric]`` (grandfathering / support lever)
2. the plan's static limit in ``workspaces.plans``

Development note: limits are rendered but not wired into the API until Paddle
is live, so nobody gets blocked with no way to pay.
"""
from workspaces.plans import UNLIMITED, get_limit, get_plan, has_feature


class PlanLimitExceeded(Exception):
    def __init__(self, metric, current, limit):
        self.metric = metric
        self.current = current
        self.limit = limit
        super().__init__(f'Plan limit reached for {metric}: {current}/{limit}')

    def to_payload(self):
        return {
            'error': 'plan_limit_reached',
            'metric': self.metric,
            'current': self.current,
            'limit': self.limit,
            'upgrade_url': '/pricing',
        }


class FeatureDisabled(Exception):
    def __init__(self, feature):
        self.feature = feature
        super().__init__(f'Feature not available on this plan: {feature}')

    def to_payload(self):
        return {
            'error': 'feature_not_available',
            'feature': self.feature,
            'upgrade_url': '/pricing',
        }


def usage(subscription, metric, current):
    """Whether ``current`` usage is still within the plan.

    ``current`` is the post-action count, so a limit of 1 allows current == 1
    and rejects current == 2.
    """
    limit = get_limit(subscription.plan, metric, subscription.limit_overrides)
    if limit == UNLIMITED:
        return True, limit
    return current <= limit, limit


def enforce(subscription, metric, current):
    """Raise PlanLimitExceeded when ``current`` would exceed the metric limit.

    ``current`` should be the post-action count (i.e. current usage + the
    increment about to happen).
    """
    allowed, limit = usage(subscription, metric, current)
    if not allowed:
        raise PlanLimitExceeded(metric, current, limit)
    return True


def enforce_feature(subscription, feature):
    if not has_feature(subscription.plan, feature):
        raise FeatureDisabled(feature)
    return True


def describe(subscription):
    """Plan + resolved limits for the pricing and account pages."""
    plan = get_plan(subscription.plan)
    resolved = {
        metric: get_limit(subscription.plan, metric, subscription.limit_overrides)
        for metric in plan['limits']
    }
    return {
        'plan': subscription.plan,
        'interval': subscription.interval,
        'status': subscription.status,
        'label': plan['label'],
        'features': dict(plan['features']),
        'limits': resolved,
        'monthly_cents': plan['monthly_cents'],
        'annual_price_cents': plan['annual_price_cents'],
        'current_period_end': subscription.current_period_end,
    }