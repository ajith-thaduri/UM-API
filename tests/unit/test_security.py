import pytest
from unittest.mock import patch
from app.core.security import validate_secret_key
from app.core.config import settings

def test_validate_secret_key_production_warning():
    """Test secret key validation in production."""
    with patch.object(settings, 'SECRET_KEY', 'your-secret-key-change-this-in-production'):
        with patch.object(settings, 'ENVIRONMENT', 'production'):
            # Should not raise, just log warning
            validate_secret_key()
            # Test passes if no exception

def test_validate_secret_key_development():
    """Test secret key validation in development."""
    with patch.object(settings, 'SECRET_KEY', 'your-secret-key-change-this-in-production'):
        with patch.object(settings, 'ENVIRONMENT', 'development'):
            # Should be fine in development
            validate_secret_key()
            # Test passes if no exception
