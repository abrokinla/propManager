import json
import logging
import urllib.request
import base64
from django.conf import settings

logger = logging.getLogger(__name__)

BREVO_URL = 'https://api.brevo.com/v3/smtp/email'


def send_email(to, subject, html_body, attachment_bytes=None, attachment_filename=None, attachment_mime='application/pdf'):
    api_key = settings.BREVO_API_KEY
    if not api_key:
        logger.info(f"[console email] To: {to} | Subject: {subject}")
        return True

    payload = {
        'sender': {'email': settings.DEFAULT_FROM_EMAIL},
        'to': [{'email': to}],
        'subject': subject,
        'htmlContent': html_body,
    }

    if attachment_bytes and attachment_filename:
        payload['attachment'] = [{
            'content': base64.b64encode(attachment_bytes).decode(),
            'name': attachment_filename,
        }]

    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        BREVO_URL,
        data=data,
        headers={
            'api-key': api_key,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        },
        method='POST',
    )

    try:
        resp = urllib.request.urlopen(req, timeout=30)
        logger.info(f"Email sent to {to}, status={resp.status}")
        return True
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors='replace')
        logger.error(f"Brevo API error {e.code}: {body}")
        return False
    except Exception as e:
        logger.error(f"Email error: {e}")
        return False
