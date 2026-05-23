import logging
from properties.models import QuitNotice, Reminder
from properties.services.pdf_service import generate_quit_notice
from properties.services.storage_service import upload_file_bytes
from properties.services.email_service import send_email

logger = logging.getLogger(__name__)


def issue_quit_notice(tenant, reason: str = None, upload_base_url: str = None) -> QuitNotice:
    notice = QuitNotice.objects.create(
        tenant=tenant,
        reason=reason,
    )

    pdf_bytes = generate_quit_notice(
        tenant_name=tenant.name,
        unit_number=tenant.unit.unit_number,
        property_name=tenant.unit.property.name,
        notice_date=notice.notice_date,
        effective_date=notice.effective_date,
        reason=reason,
    )
    filename = f"quit_notice_{tenant.id}_{tenant.name.replace(' ', '_')}.pdf"
    file_url = upload_file_bytes(pdf_bytes, filename)
    notice.document_url = file_url
    notice.save(update_fields=['document_url'])

    tenant.tenancy_status = 'quit_notice_issued'
    tenant.save(update_fields=['tenancy_status'])

    subject = f"Quit Notice - {tenant.unit.property.name} (Unit {tenant.unit.unit_number})"
    html_body = f"""
    <p>Dear {tenant.name},</p>
    <p>Please find attached a formal quit notice for your tenancy at <b>{tenant.unit.property.name}</b> (Unit <b>{tenant.unit.unit_number}</b>).</p>
    <p><b>Notice Date:</b> {notice.notice_date}<br/>
    <b>Effective Date:</b> {notice.effective_date}</p>
    <p>You are required to vacate the premises on or before the effective date stated above.</p>
    <p>Regards,<br/>PropManager</p>
    """
    success = send_email(tenant.email, subject, html_body, pdf_bytes, filename)

    Reminder.objects.create(
        tenant=tenant,
        channel='email',
        reminder_type='quit_notice',
        delivery_status='delivered' if success else 'failed',
        message=f"Quit notice sent to {tenant.email}, effective {notice.effective_date}",
    )

    return notice
