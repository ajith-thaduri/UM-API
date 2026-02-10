import pytest
from app.core.exceptions import (
    BaseAppException,
    NotFoundException,
    ValidationException,
    ConflictException,
    UnauthorizedException,
    ForbiddenException,
    InternalServerException
)

def test_base_app_exception():
    """Test BaseAppException creation."""
    exc = BaseAppException(status_code=400, detail="Test error")
    assert exc.status_code == 400
    assert exc.detail == "Test error"

def test_not_found_exception():
    """Test NotFoundException."""
    exc = NotFoundException()
    assert exc.status_code == 404
    assert exc.detail == "Resource not found"

def test_not_found_exception_with_resource_type():
    """Test NotFoundException with resource type."""
    exc = NotFoundException(resource_type="User")
    assert exc.status_code == 404
    assert exc.detail == "User not found"

def test_validation_exception():
    """Test ValidationException."""
    exc = ValidationException("Invalid input")
    assert exc.status_code == 400
    assert exc.detail == "Invalid input"

def test_conflict_exception():
    """Test ConflictException."""
    exc = ConflictException("Resource already exists")
    assert exc.status_code == 409
    assert exc.detail == "Resource already exists"

def test_unauthorized_exception():
    """Test UnauthorizedException."""
    exc = UnauthorizedException()
    assert exc.status_code == 401
    assert exc.detail == "Unauthorized"

def test_forbidden_exception():
    """Test ForbiddenException."""
    exc = ForbiddenException()
    assert exc.status_code == 403
    assert exc.detail == "Forbidden"

def test_internal_server_exception():
    """Test InternalServerException."""
    exc = InternalServerException("Database error")
    assert exc.status_code == 500
    assert exc.detail == "Database error"
