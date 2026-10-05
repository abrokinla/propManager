"""Backfill organizations for users created before the workspaces app existed.

Existing users keep their current property count via
``Subscription.limit_overrides['properties']`` so nobody gets cut off when the
free-tier limit starts being enforced.

Self-contained on purpose: historical migrations must not import live service
code, otherwise a later refactor breaks re-running this migration.
"""
import uuid

from django.db import migrations
from django.utils import timezone
from django.utils.text import slugify


def _provision(apps, user):
    Organization = apps.get_model('workspaces', 'Organization')
    OrganizationMembership = apps.get_model('workspaces', 'OrganizationMembership')
    Subscription = apps.get_model('workspaces', 'Subscription')
    AgentKYC = apps.get_model('workspaces', 'AgentKYC')

    org = Organization.objects.filter(
        memberships__user_id=user.id, kind='personal'
    ).first()
    if org is not None:
        return org

    full_name = f'{user.first_name or ""} {user.last_name or ""}'.strip()
    name = full_name or user.username
    org = Organization.objects.create(
        name=name,
        slug=f'{slugify(name)[:60]}-{uuid.uuid4().hex[:6]}',
        kind='personal',
        track='owner',
        currency='USD',
    )
    OrganizationMembership.objects.get_or_create(
        organization_id=org.id,
        user_id=user.id,
        defaults={'role': 'owner', 'accepted_at': timezone.now()},
    )
    Subscription.objects.get_or_create(
        organization_id=org.id, defaults={'plan': 'owner_free'}
    )
    AgentKYC.objects.get_or_create(user_id=user.id)
    return org


def forwards(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    Property = apps.get_model('properties', 'Property')
    OrganizationMembership = apps.get_model('workspaces', 'OrganizationMembership')
    Subscription = apps.get_model('workspaces', 'Subscription')
    PropertyMembership = apps.get_model('workspaces', 'PropertyMembership')

    for user in User.objects.all().iterator():
        org = _provision(apps, user)

        props = list(Property.objects.filter(owner_id=user.id))
        if props:
            Property.objects.filter(pk__in=[p.pk for p in props]).update(
                organization_id=org.id
            )
            for prop in props:
                PropertyMembership.objects.get_or_create(
                    property_id=prop.id,
                    user_id=user.id,
                    defaults={'role': 'manager', 'can_list': True, 'can_edit': True},
                )

        membership, _ = OrganizationMembership.objects.get_or_create(
            organization_id=org.id,
            user_id=user.id,
            defaults={'role': 'owner'},
        )
        # Legacy members are implicitly accepted; without this they would be
        # invisible to accessible_properties().
        if membership.accepted_at is None:
            membership.accepted_at = timezone.now()
            membership.save(update_fields=['accepted_at'])

        # Grandfather: preserve the current property count on the free tier.
        sub = Subscription.objects.filter(organization_id=org.id).first()
        if sub is None:
            sub = Subscription.objects.create(
                organization_id=org.id, plan='owner_free'
            )
        count = Property.objects.filter(organization_id=org.id).count()
        overrides = dict(sub.limit_overrides or {})
        overrides['properties'] = count
        sub.limit_overrides = overrides
        sub.save(update_fields=['limit_overrides'])


def backwards(apps, schema_editor):
    Property = apps.get_model('properties', 'Property')
    Organization = apps.get_model('workspaces', 'Organization')
    Subscription = apps.get_model('workspaces', 'Subscription')

    # Deliberately non-destructive. Organization has CASCADE to Property, so
    # deleting orgs here would take real user data with them. Unlink the
    # properties and clear the grandfathering overrides instead; re-running
    # forwards re-links everything through _provision().
    Property.objects.exclude(organization_id=None).update(organization=None)
    Subscription.objects.update(limit_overrides={})


class Migration(migrations.Migration):
    dependencies = [
        (
            'properties',
            '0020_property_organization_userprofile_agent_public_slug_and_more',
        ),
        ('workspaces', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]