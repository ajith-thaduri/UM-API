"""Rate limiting middleware"""

from typing import Callable
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
import time
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple in-memory rate limiter (for production, use Redis-based solution)"""
    
    def __init__(self, requests_per_minute: int = 60, requests_per_hour: int = 1000):
        """
        Initialize rate limiter
        
        Args:
            requests_per_minute: Maximum requests per minute per IP
            requests_per_hour: Maximum requests per hour per IP
        """
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        # Store request timestamps per IP: {ip: [timestamps]}
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._cleanup_interval = 300  # Clean up old entries every 5 minutes
        self._last_cleanup = time.time()
    
    def _cleanup_old_entries(self):
        """Remove timestamps older than 1 hour"""
        current_time = time.time()
        if current_time - self._last_cleanup > self._cleanup_interval:
            cutoff_time = current_time - 3600  # 1 hour ago
            for ip in list(self._requests.keys()):
                self._requests[ip] = [ts for ts in self._requests[ip] if ts > cutoff_time]
                if not self._requests[ip]:
                    del self._requests[ip]
            self._last_cleanup = current_time
    
    def is_allowed(self, ip: str) -> tuple[bool, dict]:
        """
        Check if request is allowed
        
        Returns:
            Tuple of (is_allowed, info_dict)
        """
        self._cleanup_old_entries()
        
        current_time = time.time()
        requests = self._requests[ip]
        
        # Remove requests older than 1 hour
        one_hour_ago = current_time - 3600
        requests = [ts for ts in requests if ts > one_hour_ago]
        self._requests[ip] = requests
        
        # Count requests in last minute and hour
        one_minute_ago = current_time - 60
        requests_last_minute = [ts for ts in requests if ts > one_minute_ago]
        requests_last_hour = len(requests)
        
        # Check limits
        allowed = (
            len(requests_last_minute) < self.requests_per_minute and
            requests_last_hour < self.requests_per_hour
        )
        
        if allowed:
            # Add current request
            requests.append(current_time)
            self._requests[ip] = requests
        
        info = {
            "requests_last_minute": len(requests_last_minute),
            "requests_last_hour": requests_last_hour,
            "limit_per_minute": self.requests_per_minute,
            "limit_per_hour": self.requests_per_hour
        }
        
        return allowed, info


# Global rate limiter instance
_rate_limiter = RateLimiter(
    requests_per_minute=60,  # 60 requests per minute
    requests_per_hour=1000   # 1000 requests per hour
)


def get_client_ip(request: Request) -> str:
    """Get client IP address from request"""
    # Check for forwarded IP (from proxy/load balancer)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP (original client)
        return forwarded_for.split(",")[0].strip()
    
    # Check for real IP header
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    
    # Fallback to direct client IP
    if request.client:
        return request.client.host
    
    return "unknown"


async def rate_limit_middleware(request: Request, call_next: Callable):
    """Rate limiting middleware"""
    # Skip rate limiting for health checks, docs, and OPTIONS requests
    if request.method == "OPTIONS" or request.url.path in ["/", "/health", "/api/docs", "/api/redoc", "/api/openapi.json"]:
        return await call_next(request)
    
    # Check if running in test environment
    from app.core.config import settings
    if settings.ENVIRONMENT == "testing":
        return await call_next(request)
    
    # Get client IP
    client_ip = get_client_ip(request)
    
    # Check rate limit
    allowed, info = _rate_limiter.is_allowed(client_ip)
    
    if not allowed:
        logger.warning(f"Rate limit exceeded for IP {client_ip}: {info}")
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "error": "Rate limit exceeded",
                "detail": f"Too many requests. Limit: {info['limit_per_minute']}/min, {info['limit_per_hour']}/hour",
                "retry_after": 60
            },
            headers={
                "X-RateLimit-Limit-Minute": str(info['limit_per_minute']),
                "X-RateLimit-Limit-Hour": str(info['limit_per_hour']),
                "X-RateLimit-Remaining-Minute": str(max(0, info['limit_per_minute'] - info['requests_last_minute'])),
                "X-RateLimit-Remaining-Hour": str(max(0, info['limit_per_hour'] - info['requests_last_hour'])),
                "Retry-After": "60"
            }
        )
    
    # Add rate limit headers to response
    response = await call_next(request)
    response.headers["X-RateLimit-Limit-Minute"] = str(info['limit_per_minute'])
    response.headers["X-RateLimit-Limit-Hour"] = str(info['limit_per_hour'])
    response.headers["X-RateLimit-Remaining-Minute"] = str(max(0, info['limit_per_minute'] - info['requests_last_minute']))
    response.headers["X-RateLimit-Remaining-Hour"] = str(max(0, info['limit_per_hour'] - info['requests_last_hour']))
    
    return response


