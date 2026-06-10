import logging
import re
import secrets
import string
from django.conf import settings
from django.contrib.auth.models import User
from properties.models import Tenant, Reminder
from properties.services.email_service import send_email

logger = logging.getLogger(__name__)


def _generate_username(email: str) -> str:
    base = email.split('@')[0]
    username = re.sub(r'[^a-zA-Z0-9_]', '_', base)[:30]
    if not User.objects.filter(username=username).exists():
        return username
    for suffix in range(1, 1000):
        candidate = f"{username}{suffix}"[:30]
        if not User.objects.filter(username=candidate).exists():
            return candidate
    return username  # fallback, will likely fail


def _generate_password(length=12) -> str:
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def send_invitation(tenant: Tenant, frontend_url: str = None) -> bool:
    if tenant.user:
        logger.info(f"Tenant {tenant.id} already has a user account")
        return True

    password = _generate_password()
    username = _generate_username(tenant.email or tenant.name)
    first_name = (tenant.name or '').split()[0] if tenant.name else ''
    last_name = ' '.join((tenant.name or '').split()[1:]) if tenant.name and len(tenant.name.split()) > 1 else ''

    user = User.objects.create_user(
        username=username,
        email=tenant.email or '',
        password=password,
        first_name=first_name,
        last_name=last_name,
    )
    tenant.user = user
    tenant.tenancy_status = 'invited'
    tenant.save(update_fields=['user', 'tenancy_status'])

    base_url = (frontend_url or getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')).rstrip('/')
    login_url = f"{base_url}/tenant/login"

    subject = f"Welcome to PropManager - {tenant.unit.property.name}"
    html_body = f"""
    <p>Dear {tenant.name},</p>
    <p>Your tenancy profile for <b>{tenant.unit.property.name}</b> (Unit <b>{tenant.unit.unit_number}</b>) has been created.</p>
    <p>Please log in to complete your profile and review your tenancy agreement:</p>
    <p><a href="{login_url}" style="display:inline-block;padding:12px 24px;background:#1a73e8;color:#fff;text-decoration:none;border-radius:6px;">Complete Your Profile</a></p>
    <p><b>Email:</b> {tenant.email}<br/>
    <b>Password:</b> {password}</p>
    <p>Please change your password after logging in.</p>
    <p>Regards,<br/>PropManager</p>
    """

    success = send_email(tenant.email, subject, html_body)

    Reminder.objects.create(
        tenant=tenant,
        channel='email',
        reminder_type='tenant_invite',
        delivery_status='delivered' if success else 'failed',
        message=f"Invitation sent to {tenant.email}",
    )

    return success


def resend_invitation(tenant: Tenant, frontend_url: str = None) -> bool:
    if not tenant.user:
        return send_invitation(tenant, frontend_url)

    password = _generate_password()
    tenant.user.set_password(password)
    tenant.user.save(update_fields=['password'])

    base_url = (frontend_url or getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')).rstrip('/')
    login_url = f"{base_url}/tenant/login"

    subject = f"PropManager Login Details - {tenant.unit.property.name}"
    html_body = f"""
    <p>Dear {tenant.name},</p>
    <p>Here are your updated login details for <b>{tenant.unit.property.name}</b> (Unit <b>{tenant.unit.unit_number}</b>):</p>
    <p><a href="{login_url}" style="display:inline-block;padding:12px 24px;background:#1a73e8;color:#fff;text-decoration:none;border-radius:6px;">Log In Now</a></p>
    <p><b>Email:</b> {tenant.email}<br/>
    <b>Password:</b> {password}</p>
    <p>Regards,<br/>PropManager</p>
    """

    success = send_email(tenant.email, subject, html_body)

    Reminder.objects.create(
        tenant=tenant,
        channel='email',
        reminder_type='tenant_invite',
        delivery_status='delivered' if success else 'failed',
        message=f"Invitation resent to {tenant.email}",
    )

    return success
