import logging
from django.conf import settings
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition

logger = logging.getLogger(__name__)


def send_email(to, subject, html_body, attachment_bytes=None, attachment_filename=None, attachment_mime='application/pdf'):
    if settings.SENDGRID_API_KEY:
        message = Mail(
            from_email=settings.DEFAULT_FROM_EMAIL,
            to_emails=to,
            subject=subject,
            html_content=html_body,
        )
        if attachment_bytes and attachment_filename:
            import base64
            encoded = base64.b64encode(attachment_bytes).decode()
            attachment = Attachment(
                FileContent(encoded),
                FileName(attachment_filename),
                FileType(attachment_mime),
                Disposition('attachment'),
            )
            message.add_attachment(attachment)
        try:
            sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
            response = sg.send(message)
            logger.info(f"Email sent to {to}, status={response.status_code}")
            return response.status_code == 202
        except Exception as e:
            logger.error(f"SendGrid error: {e}")
            return False
    else:
        logger.info(f"[console email] To: {to} | Subject: {subject}")
        return True
