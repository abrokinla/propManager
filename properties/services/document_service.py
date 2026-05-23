import logging
from django.utils import timezone
from properties.models import TenancyDocument, Reminder
from properties.services.pdf_service import generate_tenancy_agreement
from properties.services.storage_service import upload_file_bytes
from properties.services.email_service import send_email

logger = logging.getLogger(__name__)


UPLOAD_URL_FORMAT = "{base}/upload-document/{token}"


def send_tenancy_document(document: TenancyDocument, upload_base_url: str):
    tenant = document.tenant
    pdf_bytes = generate_tenancy_agreement(document.document_data)
    filename = f"tenancy_agreement_{tenant.id}_{tenant.name.replace(' ', '_')}.pdf"
    file_url = upload_file_bytes(pdf_bytes, filename)
    document.file_url = file_url
    document.status = 'sent'
    document.sent_at = timezone.now()
    document.save()

    tenant.tenancy_status = 'document_sent'
    tenant.save(update_fields=['tenancy_status'])

    upload_url = UPLOAD_URL_FORMAT.format(base=upload_base_url, token=document.access_token)
    subject = f"Tenancy Agreement for {tenant.unit.property.name} - Unit {tenant.unit.unit_number}"
    html_body = f"""
    <p>Dear {tenant.name},</p>
    <p>Your tenancy agreement for <b>{tenant.unit.property.name}</b> (Unit <b>{tenant.unit.unit_number}</b>) is ready.</p>
    <p>Please find the agreement attached to this email. Review the terms, print, sign, and upload the signed copy using the link below:</p>
    <p><a href="{upload_url}">{upload_url}</a></p>
    <p>If you have any questions, please contact your property manager.</p>
    <p>Regards,<br/>PropManager</p>
    """
    success = send_email(tenant.email, subject, html_body, pdf_bytes, filename)

    Reminder.objects.create(
        tenant=tenant,
        channel='email',
        reminder_type='document_sign',
        delivery_status='delivered' if success else 'failed',
        message=f"Tenancy agreement sent to {tenant.email}",
    )

    return document
