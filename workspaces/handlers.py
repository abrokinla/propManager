"""API exception handling for plan limits and feature gates.

Wired up so ``enforce()`` raising PlanLimitExceeded surfaces as HTTP 402 with
an upgrade payload. Not attached to any ViewSet yet: enforcement turns on in
Phase 8 once payments exist, otherwise users hit a wall with no way to pay.
"""
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from workspaces.services.limits import FeatureDisabled, PlanLimitExceeded


def plan_exception_handler(exc, context):
    if isinstance(exc, PlanLimitExceeded):
        return Response(exc.to_payload(), status=status.HTTP_402_PAYMENT_REQUIRED)
    if isinstance(exc, FeatureDisabled):
        return Response(exc.to_payload(), status=status.HTTP_403_FORBIDDEN)
    return exception_handler(exc, context)