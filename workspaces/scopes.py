"""Organization-scoped query helpers.

Phase 1 only adds these; ``properties/views.py`` still uses ``owner=request.user``
until Phase 2 replaces those call sites one at a time. Having the helpers here
and tested first means each ViewSet refactor is a mechanical substitution.
"""
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


def accessible_properties(user):
    """Properties the user can reach via accepted org membership."""
    return (
        Property.objects.filter(
            organization__memberships__user=user,
            organization__memberships__accepted_at__isnull=False,
        )
        .distinct()
    )


def can_access_property(user, prop):
    if OrganizationMembership.objects.filter(
        organization_id=prop.organization_id,
        user=user,
        accepted_at__isnull=False,
    ).exists():
        return True
    return prop.property_memberships.filter(user=user).exists()