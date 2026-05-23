import uuid
from datetime import date, timedelta
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('owner', 'Property Owner'),
        ('manager', 'Property Manager'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='owner')
    phone = models.CharField(max_length=20, blank=True)
    company_name = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.role}"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()


class Property(models.Model):
    PROPERTY_TYPES = [
        ('Apartment', 'Apartment'),
        ('House', 'House'),
        ('Condo', 'Condo'),
        ('Commercial', 'Commercial'),
        ('Villa', 'Villa'),
        ('Townhouse', 'Townhouse'),
        ('Studio', 'Studio'),
    ]

    name = models.CharField(max_length=200)
    address = models.TextField()
    property_type = models.CharField(max_length=50, choices=PROPERTY_TYPES)
    description = models.TextField(blank=True)
    total_units = models.PositiveIntegerField(default=1)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='properties')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Unit(models.Model):
    STATUS_CHOICES = [
        ('Available', 'Available'),
        ('Occupied', 'Occupied'),
        ('Maintenance', 'Maintenance'),
        ('Unavailable', 'Unavailable'),
        ('Under Maintenance', 'Under Maintenance'),
    ]

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='units')
    unit_number = models.CharField(max_length=50)
    bedrooms = models.IntegerField(default=1)
    toilets = models.IntegerField(default=1)
    bathrooms = models.IntegerField(default=1)
    size_sqft = models.IntegerField(null=True, blank=True)
    price_sale = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    price_rent = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Available')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.property.name} - {self.unit_number}"


class Tenant(models.Model):
    TENANCY_STATUS_CHOICES = [
        ('pending_document', 'Pending Document'),
        ('document_sent', 'Document Sent'),
        ('document_signed', 'Document Signed'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('quit_notice_issued', 'Quit Notice Issued'),
    ]

    unit = models.OneToOneField(Unit, on_delete=models.CASCADE, related_name='tenant')
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    address = models.TextField(blank=True)
    annual_rent = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    tenancy_status = models.CharField(max_length=20, choices=TENANCY_STATUS_CHOICES, default='pending_document')
    lease_start_date = models.DateField(null=True, blank=True)
    lease_renewal_date = models.DateField(null=True, blank=True)
    lease_expiry_date = models.DateField(null=True, blank=True)
    move_in_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Payment(models.Model):
    PAYMENT_METHODS = [
        ('Cash', 'Cash'),
        ('Bank Transfer', 'Bank Transfer'),
        ('Credit Card', 'Credit Card'),
        ('Mobile Money', 'Mobile Money'),
        ('Cheque', 'Cheque'),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField()
    payment_method = models.CharField(max_length=50, choices=PAYMENT_METHODS)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    years_covered = models.IntegerField(default=1)
    reference = models.CharField(max_length=200, blank=True, default='')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.tenant.name} - {self.amount}"


class TenancyDocument(models.Model):
    DOCUMENT_STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('viewed', 'Viewed'),
        ('signed', 'Signed'),
        ('completed', 'Completed'),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=50, default='tenancy_agreement')
    status = models.CharField(max_length=20, choices=DOCUMENT_STATUS_CHOICES, default='draft')
    document_data = models.JSONField(default=dict)
    file_url = models.URLField(null=True, blank=True)
    signed_file_url = models.URLField(null=True, blank=True)
    access_token = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    sent_at = models.DateTimeField(null=True, blank=True)
    signed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.tenant.name} - {self.document_type}"


class Reminder(models.Model):
    CHANNEL_CHOICES = [
        ('email', 'Email'),
    ]
    REMINDER_TYPE_CHOICES = [
        ('lease_expiry', 'Lease Expiry'),
        ('rent_due', 'Rent Due'),
        ('quit_notice', 'Quit Notice'),
        ('document_sign', 'Document Sign'),
    ]
    DELIVERY_STATUS_CHOICES = [
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='reminders')
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default='email')
    reminder_type = models.CharField(max_length=20, choices=REMINDER_TYPE_CHOICES)
    sent_at = models.DateTimeField(auto_now_add=True)
    delivery_status = models.CharField(max_length=20, choices=DELIVERY_STATUS_CHOICES, default='sent')
    message = models.TextField()

    def __str__(self):
        return f"{self.tenant.name} - {self.reminder_type}"


class QuitNotice(models.Model):
    STATUS_CHOICES = [
        ('issued', 'Issued'),
        ('acknowledged', 'Acknowledged'),
        ('enforced', 'Enforced'),
        ('cancelled', 'Cancelled'),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='quit_notices')
    notice_date = models.DateField(default=date.today)
    effective_date = models.DateField()
    reason = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='issued')
    document_url = models.URLField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.effective_date:
            self.effective_date = date.today() + timedelta(days=90)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.tenant.name} - {self.notice_date}"


class MaintenanceRequest(models.Model):
    PRIORITY_CHOICES = [
        ('Low', 'Low'),
        ('Medium', 'Medium'),
        ('High', 'High'),
    ]

    STATUS_CHOICES = [
        ('Open', 'Open'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
    ]

    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='maintenance_requests')
    title = models.CharField(max_length=200)
    description = models.TextField()
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='Medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Open')
    reported_by = models.CharField(max_length=200)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.unit.unit_number} - {self.title}"
