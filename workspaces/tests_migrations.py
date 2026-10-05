"""Regression tests for the Phase 3 data migration (workspaces.0002).

These exercise the migration as a real migration cycle against a test database:
seed pre-migration data, apply, assert, roll back, assert, re-apply. A data
migration that is not idempotent will fail on Supabase and cannot be rolled
back safely, so it gets the same scrutiny as the schema.
"""
from django.contrib.auth.models import User
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

MIGRATION = ('workspaces', '0002_backfill_organizations')
PRE_MIGRATION = ('workspaces', '0001_initial')


class BackfillMigrationTests(TransactionTestCase):
    migrate_from = MIGRATION

    def _target(self):
        """Latest workspaces migration, resolved lazily.

        '__latest__' is only valid in Django 5.2+; resolving from the graph
        keeps this working regardless of Django version.
        """
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        return executor.loader.graph.leaf_nodes('workspaces')[0]

    def _migrate(self, target=None):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        if target is None:
            target = self._target()
        return executor.migrate([target]).apps

    def setUp(self):
        self.executor = MigrationExecutor(connection)
        self.executor.loader.build_graph()

        # Roll back to 0001 so the 0002 data migration is unapplied, then seed
        # legacy data through the historical models. Migrating *to* 0002 here
        # would run the backfill before any legacy data exists.
        executor = MigrationExecutor(connection)
        executor.migrate([PRE_MIGRATION])
        old_apps = executor.loader.project_state([PRE_MIGRATION]).apps

        self.legacy_user = old_apps.get_model('auth', 'User').objects.create_user(
            username='legacybig', password='pass12345'
        )
        self.legacy_small = old_apps.get_model('auth', 'User').objects.create_user(
            username='legacysmall', password='pass12345'
        )
        # Historical models don't run Property.save(), so public_slug (which is
        # generated in save()) must be set explicitly here.
        old_prop = old_apps.get_model('properties', 'Property')
        for i in range(4):
            old_prop.objects.create(
                name=f'Big {i}',
                address='A',
                property_type='House',
                owner_id=self.legacy_user.id,
                public_slug=f'big{i:011d}',
            )
        old_prop.objects.create(
            name='Small 0',
            address='A',
            property_type='House',
            owner_id=self.legacy_small.id,
            public_slug='small00000000',
        )

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_forward_backfills_orgs_and_links_properties(self):
        self._migrate()

        from workspaces.models import (
            Organization,
            OrganizationMembership,
            PropertyMembership,
            Subscription,
        )
        from properties.models import Property

        self.assertEqual(Organization.objects.count(), 2)
        self.assertEqual(Property.objects.filter(organization__isnull=False).count(), 5)
        self.assertEqual(PropertyMembership.objects.count(), 5)

        big_sub = Subscription.objects.get(organization__name='legacybig')
        self.assertEqual(big_sub.plan, 'owner_free')
        self.assertEqual(big_sub.limit_overrides['properties'], 4)

        small_sub = Subscription.objects.get(organization__name='legacysmall')
        self.assertEqual(small_sub.limit_overrides['properties'], 1)

    def test_backfilled_memberships_are_accepted(self):
        self._migrate()

        from workspaces.models import OrganizationMembership

        memberships = OrganizationMembership.objects.all()
        self.assertEqual(memberships.count(), 2)
        self.assertEqual(memberships.filter(accepted_at__isnull=True).count(), 0)

    def test_backfilled_users_can_see_their_properties(self):
        self._migrate()

        from workspaces.scopes import accessible_properties

        # Re-fetch as a live User; self.legacy_user is a historical model
        # instance and the real queryset rejects it.
        user = User.objects.get(pk=self.legacy_user.pk)
        names = set(accessible_properties(user).values_list('name', flat=True))
        self.assertEqual(len(names), 4)
        self.assertNotIn('Small 0', names)

    def test_grandfathered_user_may_exceed_free_limit(self):
        self._migrate()

        from workspaces.services.limits import enforce
        from workspaces.models import Subscription

        sub = Subscription.objects.get(organization__name='legacybig')
        self.assertTrue(enforce(sub, 'properties', 4))
        with self.assertRaises(Exception):
            enforce(sub, 'properties', 5)

    def test_migration_is_reversible(self):
        self._migrate()
        self._migrate(PRE_MIGRATION)

        from workspaces.models import Subscription
        from properties.models import Property

        # Rollback unlinks properties and clears overrides, but must NOT delete
        # organizations: Organization CASCADEs to Property, so deleting orgs
        # would destroy the user's data.
        self.assertEqual(Property.objects.filter(organization__isnull=False).count(), 0)
        self.assertEqual(
            Subscription.objects.exclude(limit_overrides={}).count(), 0
        )
        self.assertEqual(Property.objects.count(), 5)

    def test_migration_is_idempotent_across_cycles(self):
        self._migrate()
        first = self._org_snapshot()

        self._migrate(PRE_MIGRATION)
        self._migrate()
        second = self._org_snapshot()

        self.assertEqual(first, second)

    def test_rerun_does_not_duplicate_memberships(self):
        self._migrate()
        self._migrate(PRE_MIGRATION)
        self._migrate()

        from workspaces.models import OrganizationMembership, Subscription

        self.assertEqual(OrganizationMembership.objects.count(), 2)
        self.assertEqual(Subscription.objects.count(), 2)
        self.assertEqual(
            Subscription.objects.get(organization__name='legacybig')
            .limit_overrides['properties'],
            4,
        )

    def _org_snapshot(self):
        from workspaces.models import Organization, Subscription

        return sorted(
            (org.name, org.slug, org.kind, org.track)
            for org in Organization.objects.all()
        ) + sorted(
            (sub.organization.name, sub.plan, sub.limit_overrides.get('properties'))
            for sub in Subscription.objects.all()
        )