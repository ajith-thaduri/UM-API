"""OAuth service for Google authentication"""

import logging
import json
from typing import Optional, Dict, Any
from urllib.parse import urlencode
import httpx
from cryptography.fernet import Fernet
import base64

from app.core.config import settings
from app.models.user import User, AuthProvider
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

# Initialize repositories
user_repository = UserRepository()


class OAuthTokenEncryption:
    """Encrypt/decrypt OAuth tokens"""
    
    def __init__(self):
        if not settings.OAUTH_TOKEN_ENCRYPTION_KEY:
            raise ValueError("OAUTH_TOKEN_ENCRYPTION_KEY must be set")
        
        # Convert hex key to Fernet key (32 bytes -> base64)
        key_hex = settings.OAUTH_TOKEN_ENCRYPTION_KEY
        # Ensure it's exactly 64 hex chars (32 bytes)
        if len(key_hex) < 64:
            key_hex = key_hex.ljust(64, '0')
        elif len(key_hex) > 64:
            key_hex = key_hex[:64]
        
        key_bytes = bytes.fromhex(key_hex)
        # Encode to base64 for Fernet
        self.key = base64.urlsafe_b64encode(key_bytes)
        self.cipher = Fernet(self.key)
    
    def encrypt(self, token: str) -> str:
        """Encrypt OAuth token"""
        if not token:
            return ""
        try:
            return self.cipher.encrypt(token.encode()).decode()
        except Exception as e:
            logger.error(f"Error encrypting token: {e}")
            raise
    
    def decrypt(self, encrypted_token: str) -> str:
        """Decrypt OAuth token"""
        if not encrypted_token:
            return ""
        try:
            return self.cipher.decrypt(encrypted_token.encode()).decode()
        except Exception as e:
            logger.error(f"Error decrypting token: {e}")
            raise


class GoogleOAuthService:
    """Google OAuth service"""
    
    def __init__(self):
        if not settings.GOOGLE_OAUTH_ENABLED:
            raise ValueError("Google OAuth is not enabled")
        
        self.client_id = settings.GOOGLE_CLIENT_ID
        self.client_secret = settings.GOOGLE_CLIENT_SECRET
        self.redirect_uri = settings.GOOGLE_REDIRECT_URI
        
        # OAuth endpoints
        self.authorization_url = "https://accounts.google.com/o/oauth2/v2/auth"
        self.token_url = "https://oauth2.googleapis.com/token"
        self.userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
        
        # Token encryption
        try:
            self.token_encryption = OAuthTokenEncryption()
        except Exception as e:
            logger.warning(f"OAuth token encryption not available: {e}")
            self.token_encryption = None
    
    def get_authorization_url(self, state: str) -> str:
        """
        Generate Google OAuth authorization URL
        
        Args:
            state: CSRF protection token
            
        Returns:
            Authorization URL
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "offline",  # Request refresh token
            "prompt": "consent",  # Force consent screen to get refresh token
            "state": state,
        }
        
        return f"{self.authorization_url}?{urlencode(params)}"
    
    async def exchange_code_for_tokens(self, code: str) -> Dict[str, Any]:
        """
        Exchange authorization code for access token and refresh token
        
        Args:
            code: Authorization code from Google
            
        Returns:
            Dictionary with access_token, refresh_token, expires_in, etc.
        """
        # Use longer timeout for OAuth token exchange (30 seconds)
        timeout = httpx.Timeout(30.0, connect=10.0)
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.post(
                    self.token_url,
                    data={
                        "code": code,
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "redirect_uri": self.redirect_uri,
                        "grant_type": "authorization_code",
                    },
                )
                
                if response.status_code != 200:
                    logger.error(f"Token exchange failed: {response.status_code} - {response.text}")
                    raise ValueError(f"Failed to exchange code: {response.status_code} - {response.text}")
                
                return response.json()
            except httpx.TimeoutException as e:
                logger.error(f"Timeout while exchanging OAuth code: {e}")
                raise ValueError("OAuth token exchange timed out. Please try again.")
            except httpx.RequestError as e:
                logger.error(f"Network error during OAuth token exchange: {e}")
                raise ValueError(f"Network error during OAuth authentication: {str(e)}")
    
    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """
        Get user information from Google
        
        Args:
            access_token: Google access token
            
        Returns:
            User information dictionary
        """
        # Use timeout for user info request (20 seconds)
        timeout = httpx.Timeout(20.0, connect=10.0)
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.get(
                    self.userinfo_url,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                
                if response.status_code != 200:
                    logger.error(f"Failed to get user info: {response.status_code} - {response.text}")
                    raise ValueError(f"Failed to get user info: {response.status_code} - {response.text}")
                
                return response.json()
            except httpx.TimeoutException as e:
                logger.error(f"Timeout while fetching user info: {e}")
                raise ValueError("Timeout while fetching user information. Please try again.")
            except httpx.RequestError as e:
                logger.error(f"Network error while fetching user info: {e}")
                raise ValueError(f"Network error while fetching user information: {str(e)}")
    
    def encrypt_tokens(self, access_token: str, refresh_token: Optional[str]) -> tuple[str, Optional[str]]:
        """Encrypt OAuth tokens for storage"""
        if not self.token_encryption:
            # Fallback: store as-is (not recommended for production)
            logger.warning("Token encryption not available, storing tokens unencrypted")
            return access_token, refresh_token
        
        encrypted_access = self.token_encryption.encrypt(access_token)
        encrypted_refresh = self.token_encryption.encrypt(refresh_token) if refresh_token else None
        return encrypted_access, encrypted_refresh
    
    def decrypt_tokens(self, encrypted_access: Optional[str], encrypted_refresh: Optional[str]) -> tuple[str, Optional[str]]:
        """Decrypt OAuth tokens from storage"""
        if not self.token_encryption:
            return encrypted_access or "", encrypted_refresh
        
        access_token = self.token_encryption.decrypt(encrypted_access) if encrypted_access else ""
        refresh_token = self.token_encryption.decrypt(encrypted_refresh) if encrypted_refresh else None
        return access_token, refresh_token


# Singleton instance (only if enabled)
google_oauth_service: Optional[GoogleOAuthService] = None

def get_google_oauth_service() -> Optional[GoogleOAuthService]:
    """Get Google OAuth service instance"""
    global google_oauth_service
    if settings.GOOGLE_OAUTH_ENABLED:
        if google_oauth_service is None:
            google_oauth_service = GoogleOAuthService()
        return google_oauth_service
    return None
