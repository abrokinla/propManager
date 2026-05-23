import logging
import uuid
from io import BytesIO
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)


def upload_file_bytes(file_bytes: bytes, filename: str = None, content_type: str = 'application/pdf', folder: str = 'documents') -> str:
    if not filename:
        filename = f"{uuid.uuid4().hex}.pdf"
    path = f"{folder}/{filename}"
    saved_path = default_storage.save(path, ContentFile(file_bytes))
    url = default_storage.url(saved_path)
    logger.info(f"File uploaded: {url}")
    return url
