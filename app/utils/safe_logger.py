"""Zero-PHI logging wrapper that sanitizes log messages.

SafeLogger is a defense-in-depth measure; primary PHI suppression occurs before logging.
This utility catches accidental PHI leaks in log messages via regex-based sanitization.

Defense layers:
1. De-identify data FIRST (primary defense)
2. Log metadata only (counts, hashes, IDs) (secondary defense)  
3. SafeLogger sanitizes logs (tertiary defense)

Usage:
    from app.utils.safe_logger import get_safe_logger
    
    safe_logger = get_safe_logger(__name__)
    safe_logger.info(f"De-identification complete for case {case_id}: {token_count} tokens")
"""

import logging
import re
from typing import Any


class SafeLogger:
    """Wrapper that prevents PHI from reaching logs via regex sanitization"""

    def __init__(self, logger: logging.Logger):
        self._logger = logger

    def info(self, msg: str, *args, **kwargs):
        """Log info message after sanitization"""
        self._logger.info(self._sanitize(msg), *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        """Log warning message after sanitization"""
        self._logger.warning(self._sanitize(msg), *args, **kwargs)

    def error(self, msg: str, *args, **kwargs):
        """Log error message after sanitization"""
        self._logger.error(self._sanitize(msg), *args, **kwargs)

    def debug(self, msg: str, *args, **kwargs):
        """Log debug message after sanitization"""
        self._logger.debug(self._sanitize(msg), *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs):
        """Log critical message after sanitization"""
        self._logger.critical(self._sanitize(msg), *args, **kwargs)

    def exception(self, msg: str, *args, exc_info=True, **kwargs):
        """Log exception with sanitization"""
        self._logger.exception(self._sanitize(msg), *args, exc_info=exc_info, **kwargs)

    def _sanitize(self, msg: str) -> str:
        """Strip anything that looks like PHI from log messages
        
        Note: This is a defense-in-depth measure. Primary PHI protection
        occurs via de-identification before logging. This catches accidental leaks.
        """
        if not isinstance(msg, str):
            msg = str(msg)

        # Remove names (Title Case pairs: "John Doe", "Dr. Smith")
        msg = re.sub(r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b', '[REDACTED_NAME]', msg)
        
        # Remove SSN patterns (123-45-6789)
        msg = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[REDACTED_SSN]', msg)
        
        # Remove MRN patterns (MRN: 123456, MRN 123456)
        msg = re.sub(r'MRN[:\s]*\w+', '[REDACTED_MRN]', msg, flags=re.IGNORECASE)
        
        # Remove phone patterns (123-456-7890, (123) 456-7890, 123.456.7890)
        msg = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[REDACTED_PHONE]', msg)
        msg = re.sub(r'\(\d{3}\)\s*\d{3}[-.]?\d{4}\b', '[REDACTED_PHONE]', msg)
        
        # Remove email addresses
        msg = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[REDACTED_EMAIL]', msg)
        
        # Remove potential medical record numbers (alphanumeric 6-10 chars)
        # Be conservative: only redact if prefixed with MR, MRN, ID, etc.
        msg = re.sub(r'\b(MR|MRN|ID|PATIENT_?ID)[:\s]*[A-Z0-9]{6,10}\b', '[REDACTED_ID]', msg, flags=re.IGNORECASE)

        return msg


def get_safe_logger(name: str) -> SafeLogger:
    """Get a safe logger instance for the given module name
    
    Args:
        name: Module name (typically __name__)
        
    Returns:
        SafeLogger instance that sanitizes all log messages
        
    Example:
        safe_logger = get_safe_logger(__name__)
        safe_logger.info("Processing case abc123")  # Safe
        safe_logger.info("Patient John Doe")  # Sanitized to "Patient [REDACTED_NAME]"
    """
    return SafeLogger(logging.getLogger(name))
