"""Organization-scoped query helpers.

Phase 1 only adds these; ``properties/views.py`` still uses ``owner=request.user``
until Phase 2 replaces those call sites one at a time. Having the helpers here
and tested first means each ViewSet refactor is a mechanical substitution.
"""
from django.db import models

from properties.models import Property
from workspaces.models import Organization, OrganizationMembership


def active_memberships(user):
    return OrganizationMembership.objects.filter(
        user=user, accepted_at__isnull=False
    ).select_related('organization')


def organizations_for(user):
    return Organization.objects.filter(
        memberships__user=user, memberships__accepted_at__isnull=False
    ).distinct()


def organization_for(user):
    """Return the user's primary organization, or None."""
    return organizations_for(user).order_by('created_at').first()


def property_role_for(user, prop):
    """Effective role for a user on one property.

    Organization role is the baseline; a PropertyMembership narrows or widens it
    for that property alone. Returns None when the user cannot reach the
    property.

    PropertyMembership has no invite state - creating the row is the grant -
    so it is filtered on user alone, unlike OrganizationMembership.
    """
    if prop is None:
        return None

    org = prop.organization
    if org is None:
        return 'owner' if prop.owner_id == user.id else None

    org_role = None
    if org.memberships.filter(user=user, accepted_at__isnull=False).exists():
        org_role = (
            org.memberships.filter(user=user, accepted_at__isnull=False)
            .values_list('role', flat=True)
            .first()
        )
        if org_role == 'owner':
            return 'owner'

    override = prop.property_memberships.filter(user=user).first()
    if override is not None:
        return override.role

    return org_role


def can_edit_property(user, prop):
    """Whether the user may modify a property they can otherwise see."""
    org_role = property_role_for(user, prop)
    if org_role is None:
        return False
    if org_role == 'owner':
        return True

    override = prop.property_memberships.filter(user=user).first()
    if override is not None:
        return override.can_edit
    return org_role in ('admin', 'manager', 'agent')


def accessible_properties(user):
    """Properties the user can reach.

    Three sources, OR'd together:

    1. Accepted organization membership - the target model.
    2. A PropertyMembership grant on the property, for collaborators outside the
       organization. Without this the row exists but never surfaces in a list,
       which is how an explicit grant looks like a bug.
    3. Direct ownership of a property that has no organization yet. This keeps
       the Phase 2 refactor safe on rows created between deploy and backfill,
       and for any property whose org link is missing. It narrows to nothing
       once every property is linked.
    """
    return Property.objects.filter(
        models.Q(
            organization__memberships__user=user,
            organization__memberships__accepted_at__isnull=False,
        )
        | models.Q(property_memberships__user=user)
        | models.Q(organization__isnull=True, owner=user)
    ).distinct()


def can_access_property(user, prop):
    if prop.organization_id is None:
        return prop.owner_id == user.id
    if OrganizationMembership.objects.filter(
        organization_id=prop.organization_id,
        user=user,
        accepted_at__isnull=False,
    ).exists():
        return True
    return prop.property_memberships.filter(user=user).exists()


def accessible_properties_query(user, prefix=''):
    """Return a reusable Q object for filtering related models.

    ``prefix`` is the full ORM path to Property from the calling queryset: '' for
    Property itself, ``'property__'`` for Unit, ``'tenant__unit__property__'``
    for Payment. Resolves in one hop instead of materialising a Property
    queryset first.
    """
    return (
        models.Q(
            **{
                f'{prefix}organization__memberships__user': user,
                f'{prefix}organization__memberships__accepted_at__isnull': False,
            }
        )
        | models.Q(**{f'{prefix}property_memberships__user': user})
        | models.Q(
            **{f'{prefix}organization__isnull': True, f'{prefix}owner': user}
        )
    )