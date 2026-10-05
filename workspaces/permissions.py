"""Role-based access control.

Phase 2 replaced every ``owner=request.user`` filter with organization
membership, which made every accepted member able to do everything. This module
puts the role back on top of that access.

Roles, coarsest to finest:

    owner    Full control including billing and team membership.
    admin    Full control except billing.
    agent    Read/write on organization properties (agent-track staff).
    staff    Read/write on the properties they have a PropertyMembership for.
    viewer   Read only.

Safe methods are allowed for anyone who can already reach the resource. Writes
need an edit-capable role. This is why ``IsAuthenticated`` alone was never
enough: a pending invite has no accepted_at and gets nothing at all.
"""
from rest_framework.permissions import SAFE_METHODS, BasePermission

from workspaces.scopes import can_edit_property, property_role_for

#: Roles allowed to write. Anything not listed is read-only.
EDIT_ROLES = {'owner', 'admin', 'agent', 'manager', 'staff'}
ADMIN_ROLES = {'owner', 'admin'}


def role_on(user, obj):
    """Resolve a user's role against a property-bearing object."""
    return property_role_for(user, resolve_property(obj))


def resolve_property(obj):
    """Walk from an arbitrary object to the Property that governs it.

    Returns None for organization-level objects (Organization, Subscription,
    OrganizationMembership); those are governed by the org role directly.
    """
    if obj is None:
        return None
    # Already a property.
    if hasattr(obj, 'organization_id') and hasattr(obj, 'property_memberships'):
        return obj
    for attr in ('property', 'unit', 'tenant'):
        related = getattr(obj, attr, None)
        if related is None:
            continue
        prop = resolve_property(related)
        if prop is not None:
            return prop
    return None


def resolve_organization(obj):
    """Walk from an arbitrary object to the Organization that governs it."""
    if obj is None:
        return None
    if hasattr(obj, 'memberships') and hasattr(obj, 'track'):
        return obj
    for attr in ('organization', 'property', 'unit', 'tenant'):
        related = getattr(obj, attr, None)
        if related is None:
            continue
        org = resolve_organization(related)
        if org is not None:
            return org
    return None


def org_role(user, org):
    """A user's accepted role on an organization, or None."""
    if org is None:
        return None
    return org.memberships.filter(
        user=user, accepted_at__isnull=False
    ).values_list('role', flat=True).first()


def current_owner_id(org):
    """User id of the organization's owner, or None.

    Ties break toward the most recently granted owner role (-id) so promoting a
    second owner actually transfers the mirror. Without an explicit order the
    database returns whichever row it likes, which left the mirror on the old
    owner after a handover.
    """
    if org is None:
        return None
    row = (
        org.memberships.filter(role='owner')
        .order_by('-id')
        .values_list('user_id', flat=True)
        .first()
    )
    return row


class IsWorkspaceMember(BasePermission):
    """Baseline: any accepted member with a role on the target property."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        return property_role_for(request.user, resolve_property(obj)) is not None


class CanReadWorkspace(IsWorkspaceMember):
    def has_object_permission(self, request, view, obj):
        prop = resolve_property(obj)
        role = property_role_for(request.user, prop)
        if role is None:
            return False
        if request.method in SAFE_METHODS:
            return True
        return self._can_write(request.user, prop, role)

    def _can_write(self, user, prop, role):
        if role == 'owner':
            return True
        # A per-property grant is authoritative: can_edit=False on a manager
        # membership means read-only for that property even if the org role
        # would otherwise allow writes.
        if prop is not None:
            override = prop.property_memberships.filter(user=user).first()
            if override is not None:
                return override.can_edit
        return role in EDIT_ROLES


def requested_organization_id(request):
    """organization_id the caller is trying to write into, if they named one."""
    data = getattr(request, 'data', None)
    if isinstance(data, dict) and 'organization_id' in data:
        return data.get('organization_id')
    params = getattr(request, 'query_params', None)
    if params is not None and 'organization_id' in params:
        return params.get('organization_id')
    return None


def target_organization(request):
    """The organization a write should land in, before anything is saved.

    Prefers an explicit organization_id. Without one it is the caller's primary
    organization, which is what perform_create falls back to.
    """
    from workspaces.models import Organization
    from workspaces.services.provisioning import get_organization

    org_id = requested_organization_id(request)
    if org_id:
        return Organization.objects.filter(id=org_id).first()
    return get_organization(request.user)


class CanWriteWorkspace(CanReadWorkspace):
    """For create actions, where no object exists yet.

    Scoped to the organization being written into, not "any org the user has an
    edit role on". A viewer on a team workspace still owns a personal workspace,
    and an unscoped check would let them create through the team they cannot
    write to - while perform_create would file it under whichever org it picked.
    """

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if request.method in SAFE_METHODS:
            return True

        # Update, partial_update, and destroy are checked per object in
        # has_object_permission, which is the only layer that can see a
        # PropertyMembership override. Denying here on the organization role
        # would make those overrides unreachable: a viewer with can_edit=True on
        # one property would be refused before the object was ever loaded.
        if getattr(view, 'action', None) in ('update', 'partial_update', 'destroy'):
            return True

        # create: no object yet, so the target org is all we have to go on.
        return org_role(request.user, target_organization(request)) in EDIT_ROLES


class IsWorkspaceAdmin(BasePermission):
    """Billing, team membership, and organization settings."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        org = resolve_organization(obj)
        return org_role(request.user, org) in ADMIN_ROLES


def role_for_request(user, obj):
    """Convenience helper for views that need the role inline."""
    return property_role_for(user, resolve_property(obj))


def can_edit(user, obj):
    return can_edit_property(user, resolve_property(obj))