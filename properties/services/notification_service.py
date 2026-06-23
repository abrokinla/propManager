import logging
from django.conf import settings
from ..models import Notification
from .email_service import send_email

logger = logging.getLogger(__name__)


def notify(recipient, type, title, message, link='', send_email_flag=True, email_subject=None, email_body=None):
    if not recipient:
        return
    Notification.objects.create(
        recipient=recipient,
        type=type,
        title=title,
        message=message,
        link=link,
    )
    if send_email_flag and recipient.email:
        try:
            send_email(
                to=recipient.email,
                subject=email_subject or title,
                html_body=email_body or f'<p>{message}</p>',
            )
        except Exception as e:
            logger.exception(f"Failed to send notification email to {recipient.email}: {e}")
