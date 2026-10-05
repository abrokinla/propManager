import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Organization(models.Model):
    KIND_CHOICES = [
        ('personal', 'Personal'),
        ('team', 'Team'),
    ]
    TRACK_CHOICES = [
        ('agent', 'Agent'),
        ('owner', 'Owner'),
    ]

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=80, unique=True, blank=True)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default='personal')
    track = models.CharField(max_length=10, choices=TRACK_CHOICES, default='owner')
    country = models.CharField(max_length=2, default='NG')
    currency = models.CharField(max_length=3, default='USD')
    billing_country = models.CharField(max_length=2, null=True, blank=True)
    billing_entity = models.CharField(max_length=120, null=True, blank=True)
    whatsapp = models.CharField(max_length=20, blank=True)
    bio = models.TextField(blank=True, default='')
    timezone = models.CharField(max_length=64, default='UTC')
    logo_url = models.URLField(max_length=500, blank=True, default='')
    brand_color = models.CharField(max_length=7, default='#10b981')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:70] or uuid.uuid4().hex[:12]
            base = self.slug
            counter = 2
            while Organization.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f'{base}-{counter}'
                counter += 1
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class OrganizationMembership(models.Model):
    ROLE_CHOICES = [
        ('owner', 'Owner'),
        ('admin', 'Admin'),
        ('agent', 'Agent'),
        ('staff', 'Staff'),
        ('viewer', 'Viewer'),
    ]

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='memberships'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='workspace_memberships'
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='owner')
    invited_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('organization', 'user')]
        indexes = [models.Index(fields=['user', 'accepted_at'])]

    def accept(self):
        if not self.accepted_at:
            self.accepted_at = timezone.now()
            self.save(update_fields=['accepted_at'])
        return self

    def __str__(self):
        return f'{self.user.username} @ {self.organization.name} ({self.role})'


class PropertyMembership(models.Model):
    ROLE_CHOICES = [
        ('manager', 'Manager'),
        ('staff', 'Staff'),
        ('viewer', 'Viewer'),
    ]

    property = models.ForeignKey(
        'properties.Property', on_delete=models.CASCADE, related_name='property_memberships'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='property_access'
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='manager')
    can_list = models.BooleanField(default=False)
    can_edit = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('property', 'user')]

    def __str__(self):
        return f'{self.user.username} -> {self.property.name} ({self.role})'


def _plan_choices():
    """Build field choices from the real plan definitions.

    Generated from a hardcoded track x tier grid this used to also offer
    'agent_enterprise' and 'owner_agency', which exist in no plan table and
    silently fell back to owner_free in get_plan().
    """
    from workspaces.plans import PLANS

    choices = []
    for track, track_label in (('agent', 'Agent'), ('owner', 'Owner')):
        for key, plan in PLANS.items():
            if key.startswith(f'{track}_'):
                choices.append((key, f"{track_label} {plan['label']}"))
    return choices


class Subscription(models.Model):
    PLAN_CHOICES = _plan_choices()
    INTERVAL_CHOICES = [
        ('month', 'Monthly'),
        ('year', 'Annual'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('trialing', 'Trialing'),
        ('past_due', 'Past Due'),
        ('cancelled', 'Cancelled'),
        ('paused', 'Paused'),
    ]

    organization = models.OneToOneField(
        Organization, on_delete=models.CASCADE, related_name='subscription'
    )
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default='owner_free')
    interval = models.CharField(max_length=10, choices=INTERVAL_CHOICES, default='month')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    limit_overrides = models.JSONField(default=dict, blank=True)
    billing_country = models.CharField(max_length=2, null=True, blank=True)
    billing_entity = models.CharField(max_length=120, null=True, blank=True)
    paddle_customer_id = models.CharField(max_length=255, blank=True)
    paddle_subscription_id = models.CharField(max_length=255, blank=True)
    paddle_price_id = models.CharField(max_length=255, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=['paddle_subscription_id'])]

    def __str__(self):
        return f'{self.organization.name} -> {self.plan} ({self.interval})'


class AgentKYC(models.Model):
    STATUS_CHOICES = [
        ('unsubmitted', 'Unsubmitted'),
        ('pending', 'Pending Review'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='kyc'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='unsubmitted')
    license_number = models.CharField(max_length=100, blank=True)
    documents = models.JSONField(default=dict, blank=True)
    rejection_reason = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='kyc_reviews',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.username} KYC {self.status}'