"""Workspace provisioning.

Every user gets exactly one personal Organization, an owner membership, and a
free Subscription. The function is idempotent so it can safely be called from
both the registration serializer and the post_save signal.
"""
import uuid

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.text import slugify

from workspaces.models import AgentKYC, Organization, OrganizationMembership, Subscription


def _default_org_name(user):
    name = user.get_full_name().strip()
    if not name:
        name = user.username
    return f'{name}'


FREE_PLANS = ('agent_free', 'owner_free')


@transaction.atomic
def provision_workspace(user, track='owner'):
    """Create (or return) the personal workspace for ``user``.

    Idempotent: returns the existing Organization if one already exists.

    The post_save signal provisions with the default 'owner' track, but the
    agent registration path knows the real track up front. When an existing
    workspace is still on a free tier we reconcile the track to the explicit
    value. A workspace that has moved to a paid plan keeps its track, so
    upgrading later can never silently change what someone already bought.
    """
    existing = Organization.objects.filter(
        memberships__user=user, kind='personal'
    ).first()
    if existing:
        sub = _ensure_subscription(existing)
        if existing.track != track and sub.plan in FREE_PLANS:
            existing.track = track
            existing.save(update_fields=['track'])
            sub.plan = f'{track}_free'
            sub.save(update_fields=['plan'])
        return existing

    name = _default_org_name(user)
    org = Organization.objects.create(
        name=name,
        slug=f'{slugify(name)[:60]}-{uuid.uuid4().hex[:6]}',
        kind='personal',
        track=track,
    )
    OrganizationMembership.objects.create(
        organization=org, user=user, role='owner', accepted_at=_now()
    )
    _ensure_subscription(org)
    AgentKYC.objects.get_or_create(user=user)
    return org


def _ensure_subscription(org):
    sub, _ = Subscription.objects.get_or_create(
        organization=org, defaults={'plan': f'{org.track}_free'}
    )
    return sub


def _now():
    from django.utils import timezone

    return timezone.now()


def get_organization(user):
    """Primary organization for the user, provisioning one if missing."""
    from workspaces.scopes import organization_for

    org = organization_for(user)
    if org is None:
        org = provision_workspace(user)
    return org


def get_subscription(user):
    org = get_organization(user)
    return _ensure_subscription(org)


def add_member(org, user, role='staff', accept=False):
    """Add or update a member's role on an organization."""
    membership, created = OrganizationMembership.objects.get_or_create(
        organization=org, user=user, defaults={'role': role}
    )
    if not created and membership.role != role:
        membership.role = role
        membership.save(update_fields=['role'])
    if accept and not membership.accepted_at:
        membership.accept()
    if org.kind == 'personal':
        org.kind = 'team'
        org.save(update_fields=['kind'])
    return membership


def remove_member(org, user):
    return OrganizationMembership.objects.filter(organization=org, user=user).delete()


def promote_to_team(org):
    if org.kind == 'personal':
        org.kind = 'team'
        org.save(update_fields=['kind'])
        return org
    return org