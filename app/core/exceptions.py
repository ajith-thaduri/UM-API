"""Custom exception classes for the application"""

from fastapi import HTTPException, status


class BaseAppException(HTTPException):
    """Base exception class for application-specific exceptions"""

    def __init__(
        self,
        status_code: int,
        detail: str,
        headers: dict = None,
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.detail = detail
        self.status_code = status_code


class NotFoundException(BaseAppException):
    """Exception raised when a resource is not found"""

    def __init__(self, detail: str = "Resource not found", resource_type: str = None):
        if resource_type:
            detail = f"{resource_type} not found"
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
        )


class ValidationException(BaseAppException):
    """Exception raised when validation fails"""

    def __init__(self, detail: str = "Validation error"):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        )


class ConflictException(BaseAppException):
    """Exception raised when a resource conflict occurs"""

    def __init__(self, detail: str = "Resource conflict"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )


class UnauthorizedException(BaseAppException):
    """Exception raised when authentication fails"""

    def __init__(self, detail: str = "Unauthorized"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
        )


class ForbiddenException(BaseAppException):
    """Exception raised when access is forbidden"""

    def __init__(self, detail: str = "Forbidden"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )


class InternalServerException(BaseAppException):
    """Exception raised for internal server errors"""

    def __init__(self, detail: str = "Internal server error"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
        )

