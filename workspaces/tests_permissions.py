"""Phase 6: role-based permissions on organization members.

Every test here uses a user who can already reach the property through an
accepted membership. That is the whole point: Phase 2 made access work, these
tests prove it is not unbounded.
"""
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from properties.models import Property
from workspaces.models import OrganizationMembership, PropertyMembership
from workspaces.permissions import IsWorkspaceAdmin, resolve_property
from workspaces.services.provisioning import (
    add_member,
    provision_workspace,
    remove_member,
)


class FakeRequest:
    """Minimal request stand-in for direct permission-class assertions."""

    def __init__(self, method, user):
        self.method = method
        self.user = user


class RBACTestBase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(
            username='rbowner', password='pass12345', first_name='Rita'
        )
        self.org = provision_workspace(self.owner, track='agent')
        self.prop = Property.objects.create(
            name='Org Prop', address='Lagos', property_type='House',
            organization=self.org,
        )

    def member(self, username, role):
        user = User.objects.create_user(username=username, password='pass12345')
        # Provision first so the user has their own workspace, then move them
        # onto the org; a bare membership row would leave them a second org.
        provision_workspace(user, track='agent')
        add_member(self.org, user, role=role, accept=True)
        return user

    def as_user(self, user):
        self.client.force_authenticate(user=user)
        return self.client


class PropertyRoleTests(RBACTestBase):
    def test_owner_can_create_property(self):
        self.as_user(self.owner)
        response = self.client.post(
            '/api/properties/',
            {'name': 'Second', 'address': 'Abuja', 'property_type': 'House',
             'total_units': 2},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_admin_can_create_property(self):
        self.as_user(self.member('rbadm', 'admin'))
        response = self.client.post(
            '/api/properties/',
            {'name': 'ByAdmin', 'address': 'Abuja', 'property_type': 'House',
             'total_units': 1},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_viewer_cannot_create_property(self):
        self.as_user(self.member('rbview', 'viewer'))
        response = self.client.post(
            '/api/properties/',
            {'name': 'Nope', 'address': 'Abuja', 'property_type': 'House',
             'total_units': 1},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewer_can_read_properties(self):
        self.as_user(self.member('rbview2', 'viewer'))
        self.assertEqual(
            self.client.get('/api/properties/').status_code, status.HTTP_200_OK
        )
        self.assertEqual(
            self.client.get(f'/api/properties/{self.prop.id}/').status_code,
            status.HTTP_200_OK,
        )

    def test_viewer_cannot_update_property(self):
        self.as_user(self.member('rbview3', 'viewer'))
        response = self.client.patch(
            f'/api/properties/{self.prop.id}/', {'name': 'Hacked'}
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.prop.refresh_from_db()
        self.assertEqual(self.prop.name, 'Org Prop')

    def test_viewer_cannot_delete_property(self):
        self.as_user(self.member('rbview4', 'viewer'))
        response = self.client.delete(f'/api/properties/{self.prop.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Property.objects.filter(id=self.prop.id).exists())

    def test_staff_can_update_property(self):
        self.as_user(self.member('rbstaff', 'staff'))
        response = self.client.patch(
            f'/api/properties/{self.prop.id}/', {'name': 'Updated'}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_pending_member_has_no_access(self):
        user = User.objects.create_user(username='rbpend', password='pass12345')
        provision_workspace(user, track='agent')
        add_member(self.org, user, role='admin', accept=False)
        self.as_user(user)
        self.assertEqual(
            self.client.get('/api/properties/').status_code, status.HTTP_200_OK
        )
        # The org's property is invisible; only their own workspace is empty.
        ids = [p['id'] for p in self.client.get('/api/properties/').data['results']]
        self.assertNotIn(self.prop.id, ids)
        self.assertEqual(
            self.client.get(f'/api/properties/{self.prop.id}/').status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_non_member_gets_404_on_detail(self):
        outsider = User.objects.create_user(username='rbnone', password='pass12345')
        self.as_user(outsider)
        self.assertEqual(
            self.client.get(f'/api/properties/{self.prop.id}/').status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_non_member_cannot_create_units_in_org_property(self):
        outsider = User.objects.create_user(username='rbnone2', password='pass12345')
        self.as_user(outsider)
        response = self.client.post(
            '/api/units/',
            {'property_id': self.prop.id, 'unit_number': 'X001',
             'bedrooms': 1, 'bathrooms': 1, 'price_rent': '100'},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_viewer_cannot_create_units(self):
        self.as_user(self.member('rbview5', 'viewer'))
        response = self.client.post(
            '/api/units/',
            {'property_id': self.prop.id, 'unit_number': 'Y001',
             'bedrooms': 1, 'bathrooms': 1, 'price_rent': '100'},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class PropertyMembershipOverrideTests(RBACTestBase):
    """A per-property grant outside the org, and its can_edit flag."""

    def setUp(self):
        super().setUp()
        self.outsider = User.objects.create_user(
            username='rbext', password='pass12345'
        )
        provision_workspace(self.outsider, track='agent')

    def test_property_membership_grants_access(self):
        PropertyMembership.objects.create(
            property=self.prop, user=self.outsider, role='manager',
            can_list=True, can_edit=True,
        )
        self.as_user(self.outsider)
        response = self.client.get(f'/api/properties/{self.prop.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_property_membership_appears_in_list(self):
        PropertyMembership.objects.create(
            property=self.prop, user=self.outsider, role='viewer',
            can_list=True, can_edit=False,
        )
        self.as_user(self.outsider)
        ids = [p['id'] for p in self.client.get('/api/properties/').data['results']]
        self.assertIn(self.prop.id, ids)

    def test_can_edit_false_blocks_update(self):
        PropertyMembership.objects.create(
            property=self.prop, user=self.outsider, role='manager',
            can_list=True, can_edit=False,
        )
        self.as_user(self.outsider)
        response = self.client.patch(
            f'/api/properties/{self.prop.id}/', {'name': 'Nope'}
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.prop.refresh_from_db()
        self.assertEqual(self.prop.name, 'Org Prop')

    def test_can_edit_true_allows_update(self):
        PropertyMembership.objects.create(
            property=self.prop, user=self.outsider, role='staff',
            can_list=True, can_edit=True,
        )
        self.as_user(self.outsider)
        response = self.client.patch(
            f'/api/properties/{self.prop.id}/', {'name': 'Yes'}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_org_viewer_narrowed_by_readonly_property_membership(self):
        """Org role says viewer; a can_edit membership on one property wins."""
        member = self.member('rbnarrow', 'viewer')
        PropertyMembership.objects.create(
            property=self.prop, user=member, role='manager',
            can_list=True, can_edit=True,
        )
        self.as_user(member)
        response = self.client.patch(
            f'/api/properties/{self.prop.id}/', {'name': 'Allowed'}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_removed_membership_revokes_access(self):
        pm = PropertyMembership.objects.create(
            property=self.prop, user=self.outsider, role='manager',
            can_list=True, can_edit=True,
        )
        self.as_user(self.outsider)
        self.assertEqual(
            self.client.get(f'/api/properties/{self.prop.id}/').status_code,
            status.HTTP_200_OK,
        )
        pm.delete()
        self.assertEqual(
            self.client.get(f'/api/properties/{self.prop.id}/').status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_membership_on_other_property_does_not_leak(self):
        other = Property.objects.create(
            name='Other', address='Benin', property_type='House',
            organization=self.org,
        )
        PropertyMembership.objects.create(
            property=self.prop, user=self.outsider, role='manager',
            can_list=True, can_edit=True,
        )
        self.as_user(self.outsider)
        self.assertEqual(
            self.client.get(f'/api/properties/{other.id}/').status_code,
            status.HTTP_404_NOT_FOUND,
        )


class ResolvePropertyTests(RBACTestBase):
    def test_resolves_direct_property(self):
        self.assertEqual(resolve_property(self.prop), self.prop)

    def test_resolves_unit(self):
        from properties.models import Unit

        unit = Unit.objects.create(property=self.prop, unit_number='R001')
        self.assertEqual(resolve_property(unit), self.prop)

    def test_resolves_tenant_via_unit(self):
        from properties.models import Tenant, Unit

        unit = Unit.objects.create(property=self.prop, unit_number='R002')
        tenant = Tenant.objects.create(
            name='T N', email='t@test.com', phone='0800', unit=unit,
        )
        self.assertEqual(resolve_property(tenant), self.prop)

    def test_none_for_orphan(self):
        self.assertIsNone(resolve_property(None))


class MembershipManagementPermissionTests(RBACTestBase):
    def test_viewer_fails_admin_check_on_own_membership_row(self):
        """Guards against a viewer escalating by editing membership rows."""
        member = self.member('rbesc', 'viewer')
        row = OrganizationMembership.objects.get(user=member, organization=self.org)
        request = FakeRequest('PATCH', member)
        self.assertFalse(IsWorkspaceAdmin().has_object_permission(request, member, row))

    def test_admin_passes_admin_check(self):
        admin = self.member('rbadm2', 'admin')
        row = OrganizationMembership.objects.get(user=admin, organization=self.org)
        self.assertTrue(
            IsWorkspaceAdmin().has_object_permission(FakeRequest('PATCH', admin), admin, row)
        )

    def test_staff_fails_admin_check(self):
        """Staff can edit properties but must not manage the team."""
        staff = self.member('rbstaff2', 'staff')
        self.assertFalse(
            IsWorkspaceAdmin().has_object_permission(FakeRequest('PATCH', staff), staff, self.org)
        )

    def test_owner_passes_admin_check(self):
        self.assertTrue(
            IsWorkspaceAdmin().has_object_permission(
                FakeRequest('PATCH', self.owner), self.owner, self.org
            )
        )

    def test_outsider_fails_admin_check(self):
        outsider = User.objects.create_user(username='rbadmout', password='pass12345')
        self.assertFalse(
            IsWorkspaceAdmin().has_object_permission(
                FakeRequest('PATCH', outsider), outsider, self.org
            )
        )

class OwnerMirrorSyncTests(RBACTestBase):
    """Property.owner must track the organization owner role."""

    def test_new_property_inherits_org_owner(self):
        self.assertEqual(self.prop.owner_id, self.owner.id)

    def test_granting_owner_role_moves_the_mirror(self):
        successor = self.member('rbsucc', 'admin')
        add_member(self.org, successor, role='owner', accept=True)
        self.prop.refresh_from_db()
        self.assertEqual(self.prop.owner_id, successor.id)

    def test_sync_touches_every_org_property(self):
        second = Property.objects.create(
            name='Second', address='Ibadan', property_type='House',
            organization=self.org,
        )
        successor = self.member('rbsucc2', 'admin')
        add_member(self.org, successor, role='owner', accept=True)
        self.prop.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(self.prop.owner_id, successor.id)
        self.assertEqual(second.owner_id, successor.id)

    def test_removing_last_owner_clears_mirror(self):
        remove_member(self.org, self.owner)
        self.prop.refresh_from_db()
        self.assertIsNone(self.prop.owner_id)
        self.assertTrue(Property.objects.filter(id=self.prop.id).exists())

    def test_removing_owner_with_successor_keeps_mirror(self):
        successor = self.member('rbsucc3', 'owner')
        add_member(self.org, successor, role='owner', accept=True)
        remove_member(self.org, self.owner)
        self.prop.refresh_from_db()
        self.assertEqual(self.prop.owner_id, successor.id)

    def test_refresh_owner_from_org_helper(self):
        successor = self.member('rbsucc4', 'admin')
        add_member(self.org, successor, role='owner', accept=True)
        self.assertTrue(self.prop.refresh_owner_from_org())
        self.prop.refresh_from_db()
        self.assertEqual(self.prop.owner_id, successor.id)

    def test_refresh_is_noop_when_already_current(self):
        self.assertFalse(self.prop.refresh_owner_from_org())

    def test_unlinked_property_refresh_is_noop(self):
        orphan = Property.objects.create(
            name='Orphan', address='X', property_type='House', owner=self.owner
        )
        self.assertFalse(orphan.refresh_owner_from_org())
