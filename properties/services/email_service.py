import logging
from django.conf import settings
from django.core.mail import EmailMessage

logger = logging.getLogger(__name__)


def send_email(to, subject, html_body, attachment_bytes=None, attachment_filename=None, attachment_mime='application/pdf'):
    try:
        msg = EmailMessage(
            subject=subject,
            body=html_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to],
        )
        msg.content_subtype = 'html'
        if attachment_bytes and attachment_filename:
            msg.attach(attachment_filename, attachment_bytes, attachment_mime)
        msg.send()
        logger.info(f"Email sent to {to}")
        return True
    except Exception as e:
        logger.error(f"Email error: {e}")
        return False
