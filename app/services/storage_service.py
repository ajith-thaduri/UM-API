"""Storage service factory"""

from app.core.config import settings

# Import the appropriate storage service based on configuration
if settings.STORAGE_TYPE == "s3":
    from app.services.s3_storage_service import s3_storage_service as storage_service
elif settings.STORAGE_TYPE == "local":
    from app.services.local_storage_service import local_storage_service as storage_service
else:
    raise ValueError(f"Unsupported storage type: {settings.STORAGE_TYPE}. Must be 'local' or 's3'")

