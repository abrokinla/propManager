import logging
import uuid
from io import BytesIO
import cloudinary.uploader

logger = logging.getLogger(__name__)


def upload_file_bytes(file_bytes: bytes, filename: str = None, content_type: str = 'application/pdf', folder: str = 'documents', resource_type: str = None) -> str:
    if not filename:
        filename = f"{uuid.uuid4().hex}{'.pdf' if content_type == 'application/pdf' else ''}"
    public_id = f"{folder}/{filename.rsplit('.', 1)[0]}"
    if resource_type is None:
        resource_type = 'raw' if content_type == 'application/pdf' else 'auto'
    result = cloudinary.uploader.upload(
        BytesIO(file_bytes),
        public_id=public_id,
        resource_type=resource_type,
        access_mode='public',
    )
    url = result['secure_url']
    logger.info(f"File uploaded: {url}")
    return url
