"""Security utilities and validation"""

import warnings
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)


def validate_secret_key():
    """Validate that SECRET_KEY is changed from default in production"""
    if settings.SECRET_KEY == "your-secret-key-change-this-in-production":
        if settings.ENVIRONMENT in ("production", "staging"):
            logger.warning(
                "SECRET_KEY is using default value. This is insecure for production. "
                "Please set a strong random SECRET_KEY in your environment variables."
            )
            warnings.warn(
                "SECRET_KEY is using default value. This is insecure for production.",
                UserWarning
            )
        else:
            logger.debug("SECRET_KEY using default value (acceptable for development)")


# Validate on module import (but don't fail if using default in dev)
try:
    validate_secret_key()
except Exception as e:
    logger.debug(f"Secret key validation warning (non-critical): {e}")


