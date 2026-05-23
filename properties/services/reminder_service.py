import logging
from datetime import date, timedelta
from django.db.models import Q
from properties.models import Tenant, Reminder
from properties.services.email_service import send_email

logger = logging.getLogger(__name__)


def send_reminder(tenant, reminder_type: str, channel: str = 'email') -> Reminder:
    if reminder_type == 'lease_expiry':
        subject = f"Lease Expiry Reminder - {tenant.unit.property.name}"
        html_body = f"""
        <p>Dear {tenant.name},</p>
        <p>Your lease for <b>{tenant.unit.property.name}</b> (Unit <b>{tenant.unit.unit_number}</b>) is expiring on <b>{tenant.lease_expiry_date}</b>.</p>
        <p>Please contact your property manager to discuss renewal options.</p>
        <p>Regards,<br/>PropManager</p>
        """
        message = f"Lease expiry reminder sent to {tenant.email}, expires {tenant.lease_expiry_date}"

    elif reminder_type == 'rent_due':
        subject = f"Rent Due Reminder - {tenant.unit.property.name}"
        html_body = f"""
        <p>Dear {tenant.name},</p>
        <p>This is a reminder that your rent of <b>₦{float(tenant.annual_rent or 0):,.2f}</b> (annual) for <b>{tenant.unit.property.name}</b> (Unit <b>{tenant.unit.unit_number}</b>) is due.</p>
        <p>Please ensure payment is made promptly.</p>
        <p>Regards,<br/>PropManager</p>
        """
        message = f"Rent due reminder sent to {tenant.email}"

    elif reminder_type == 'document_sign':
        subject = f"Document Signing Reminder - {tenant.unit.property.name}"
        html_body = f"""
        <p>Dear {tenant.name},</p>
        <p>Please remember to sign and return your tenancy document for <b>{tenant.unit.property.name}</b> (Unit <b>{tenant.unit.unit_number}</b>).</p>
        <p>Regards,<br/>PropManager</p>
        """
        message = f"Document signing reminder sent to {tenant.email}"

    else:
        raise ValueError(f"Unknown reminder type: {reminder_type}")

    success = send_email(tenant.email, subject, html_body)

    reminder = Reminder.objects.create(
        tenant=tenant,
        channel=channel,
        reminder_type=reminder_type,
        delivery_status='delivered' if success else 'failed',
        message=message,
    )
    return reminder


def send_due_reminders():
    today = date.today()
    sent = 0

    # Lease expiry reminders at 30, 14, 7, and 0 days before expiry
    for days_before in [30, 14, 7, 0]:
        target_date = today + timedelta(days=days_before)
        tenants = Tenant.objects.filter(
            lease_expiry_date=target_date,
            is_active=True,
            tenancy_status__in=['active', 'document_signed'],
        )
        for tenant in tenants:
            try:
                send_reminder(tenant, 'lease_expiry')
                sent += 1
                logger.info(f"Lease expiry reminder sent to {tenant.name} ({days_before}d before)")
            except Exception as e:
                logger.error(f"Failed to send lease expiry reminder to {tenant.name}: {e}")

    return sent
