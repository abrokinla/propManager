from django.contrib import admin

from workspaces.models import (
    AgentKYC,
    Organization,
    OrganizationMembership,
    PropertyMembership,
    Subscription,
)


@admin.register(AgentKYC)
class AgentKYCADmin(admin.ModelAdmin):
    """Platform-level KYC review.

    AgentKYCReviewView covers reviewing inside one agent workspace. Verifying an
    arbitrary applicant from the PropManager side is a support action, so the
    record has to be reachable here too - without it status could only ever be
    set by a colleague in the applicant's own org.
    """

    list_display = ['user', 'status', 'license_number', 'reviewed_by', 'reviewed_at']
    list_filter = ['status']
    search_fields = ['user__username', 'license_number']
    readonly_fields = ['reviewed_by', 'reviewed_at']


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['name', 'track', 'kind', 'country', 'currency', 'created_at']
    list_filter = ['track', 'kind', 'country']
    search_fields = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ['user', 'organization', 'role', 'accepted_at']
    list_filter = ['role']
    search_fields = ['user__username', 'organization__name']


@admin.register(PropertyMembership)
class PropertyMembershipAdmin(admin.ModelAdmin):
    list_display = ['user', 'property', 'role', 'can_list', 'can_edit']
    list_filter = ['role', 'can_list', 'can_edit']
    search_fields = ['user__username', 'property__name']


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    """Also where grandfathered limits get set via limit_overrides."""

    list_display = [
        'organization',
        'plan',
        'interval',
        'status',
        'paddle_customer_id',
        'paddle_subscription_id',
        'current_period_end',
    ]
    list_filter = ['plan', 'interval', 'status']
    search_fields = ['organization__name', 'paddle_customer_id', 'paddle_subscription_id']