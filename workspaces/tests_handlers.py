"""Tests for the plan-limit exception handler.

Enforcement is not attached to any endpoint yet (Phase 8), so the handler is
exercised through a throwaway view. This proves the 402 contract now, so
turning enforcement on later is a one-line settings change rather than a
retest of error shapes.
"""
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import path
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.test import APIClient

from workspaces.services.limits import enforce, enforce_feature
from workspaces.services.provisioning import provision_workspace


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def _enforce_properties(request):
    from workspaces.services.provisioning import get_subscription

    sub = get_subscription(request.user)
    current = accessible_count(request.user) + 1
    enforce(sub, 'properties', current)
    return Response({'ok': True})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def _enforce_feature(request):
    from workspaces.services.provisioning import get_subscription

    sub = get_subscription(request.user)
    enforce_feature(sub, 'whatsapp_api')
    return Response({'ok': True})


def accessible_count(user):
    from properties.models import Property
    from workspaces.scopes import accessible_properties

    return accessible_properties(user).count()


urlpatterns = [
    path('api/_test/enforce-properties/', _enforce_properties),
    path('api/_test/enforce-feature/', _enforce_feature),
]


@override_settings(ROOT_URLCONF='workspaces.tests_handlers')
class PlanLimitHandlerTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='limituser', password='pass12345')
        self.client.force_authenticate(user=self.user)

    def test_under_limit_returns_ok(self):
        response = self.client.post('/api/_test/enforce-properties/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_over_limit_returns_402_with_payload(self):
        from properties.models import Property

        # Free tier allows one property, so a second must be refused.
        Property.objects.create(
            name='Existing', address='A1', property_type='House', owner=self.user
        )
        response = self.client.post('/api/_test/enforce-properties/')
        self.assertEqual(response.status_code, status.HTTP_402_PAYMENT_REQUIRED)
        self.assertEqual(response.data['error'], 'plan_limit_reached')
        self.assertEqual(response.data['metric'], 'properties')
        self.assertEqual(response.data['limit'], 1)
        self.assertEqual(response.data['current'], 2)
        self.assertEqual(response.data['upgrade_url'], '/pricing')

    def test_grandfathered_user_is_not_blocked(self):
        sub = provision_workspace(self.user).subscription
        sub.limit_overrides = {'properties': 50}
        sub.save()
        for _ in range(3):
            response = self.client.post('/api/_test/enforce-properties/')
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_disabled_feature_returns_403(self):
        response = self.client.post('/api/_test/enforce-feature/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['error'], 'feature_not_available')
        self.assertEqual(response.data['feature'], 'whatsapp_api')

    def test_ordinary_errors_still_use_default_handling(self):
        response = self.client.get('/api/_test/enforce-properties/')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertNotIn('plan_limit_reached', response.data)