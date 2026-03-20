import pytest
from app.middleware.rate_limit import RateLimiter, get_client_ip
from fastapi import Request
from unittest.mock import MagicMock

def test_rate_limiter_allows_requests():
    """Test that rate limiter allows requests under limit."""
    limiter = RateLimiter(requests_per_minute=10, requests_per_hour=100)
    
    for i in range(5):
        allowed, info = limiter.is_allowed("127.0.0.1")
        assert allowed is True
    
    # Should still be allowed
    allowed, info = limiter.is_allowed("127.0.0.1")
    assert allowed is True
    assert info["requests_last_minute"] <= 10

def test_rate_limiter_blocks_excessive_requests():
    """Test that rate limiter blocks excessive requests."""
    limiter = RateLimiter(requests_per_minute=2, requests_per_hour=100)
    
    # Make requests up to limit
    limiter.is_allowed("127.0.0.2")
    limiter.is_allowed("127.0.0.2")
    
    # Next request should be blocked
    allowed, info = limiter.is_allowed("127.0.0.2")
    assert allowed is False
    assert info["requests_last_minute"] >= 2

def test_get_client_ip_from_forwarded_header():
    """Test getting client IP from X-Forwarded-For header."""
    request = MagicMock(spec=Request)
    request.headers = {"X-Forwarded-For": "192.168.1.1, 10.0.0.1"}
    request.client = None
    
    ip = get_client_ip(request)
    assert ip == "192.168.1.1"

def test_get_client_ip_from_real_ip_header():
    """Test getting client IP from X-Real-IP header."""
    request = MagicMock(spec=Request)
    request.headers = {"X-Real-IP": "192.168.1.2"}
    request.client = None
    
    ip = get_client_ip(request)
    assert ip == "192.168.1.2"

def test_get_client_ip_from_client():
    """Test getting client IP from request.client."""
    request = MagicMock(spec=Request)
    request.headers = {}
    request.client = MagicMock()
    request.client.host = "127.0.0.1"
    
    ip = get_client_ip(request)
    assert ip == "127.0.0.1"

def test_get_client_ip_unknown():
    """Test getting client IP when no headers available."""
    request = MagicMock(spec=Request)
    request.headers = {}
    request.client = None
    
    ip = get_client_ip(request)
    assert ip == "unknown"
