"""OAuth authentication endpoints"""

import uuid
import secrets
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.dependencies import get_user_repository
from app.repositories.user_repository import UserRepository
from app.models.user import User, AuthProvider
from app.services.oauth_service import get_google_oauth_service
from app.services.auth_service import create_access_token
from app.schemas.auth import TokenResponse
from app.core.config import settings
from jose import jwt, JWTError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/oauth", tags=["oauth"])


# Stateless OAuth state management using signed JWTs
# This avoids issues with multiple workers/instances where in-memory storage would fail


@router.get("/google/authorize")
async def google_authorize(
    request: Request,
    db: Session = Depends(get_db),
):
    """Initiate Google OAuth flow"""
    oauth_service = get_google_oauth_service()
    if not oauth_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not enabled"
        )
    
    # Generate signed state token for CSRF protection (stateless)
    from datetime import timedelta
    
    state_payload = {
        "type": "google_oauth_state",
        "exp": datetime.utcnow() + timedelta(minutes=15),
        "nonce": secrets.token_urlsafe(16)
    }
    state = jwt.encode(state_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    
    # Get authorization URL
    auth_url = oauth_service.get_authorization_url(state)
    
    # Redirect to Google
    return RedirectResponse(url=auth_url)


@router.get("/google/callback")
async def google_callback(
    code: str = Query(...),
    state: str = Query(...),
    error: str = Query(None),
    db: Session = Depends(get_db),
    user_repository: UserRepository = Depends(get_user_repository),
):
    """Handle Google OAuth callback"""
    oauth_service = get_google_oauth_service()
    if not oauth_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not enabled"
        )
    
    # Check for errors
    if error:
        logger.error(f"Google OAuth error: {error}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth error: {error}"
        )
    
    # Verify state (CSRF protection) - Stateless JWT validation
    try:
        decoded_state = jwt.decode(
            state, 
            settings.SECRET_KEY, 
            algorithms=[settings.ALGORITHM]
        )
        if decoded_state.get("type") != "google_oauth_state":
            logger.error(f"Invalid OAuth state type: {decoded_state.get('type')}")
            raise ValueError("Invalid state type")
    except (JWTError, ValueError) as e:
        logger.error(f"Invalid OAuth state: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state parameter"
        )
    
    try:
        # Exchange code for tokens
        token_data = await oauth_service.exchange_code_for_tokens(code)
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        
        if not access_token:
            raise ValueError("No access token received")
        
        # Get user info from Google
        user_info = await oauth_service.get_user_info(access_token)
        
        google_id = user_info.get("id")  # Google user ID
        email = user_info.get("email")
        name = user_info.get("name", email.split("@")[0] if email else "User")
        picture = user_info.get("picture")
        verified_email = user_info.get("verified_email", False)
        
        if not email:
            raise ValueError("No email in user info")
        
        # Encrypt tokens for storage
        encrypted_access, encrypted_refresh = oauth_service.encrypt_tokens(
            access_token, refresh_token
        )
        
        # Find or create user
        user = user_repository.get_by_email(db, email)
        
        if user:
            # Existing user - update OAuth info
            # Normalize auth_provider for comparison (handle case differences and None)
            current_provider = (user.auth_provider or "").lower().strip()
            password_value = AuthProvider.PASSWORD.value.lower()
            google_value = AuthProvider.GOOGLE.value.lower()
            
            logger.info(f"Existing user found: {email}, current auth_provider: '{user.auth_provider}'")
            
            if current_provider == password_value or current_provider == "" or user.auth_provider is None:
                # User exists with password auth (or no provider set) - link Google account
                logger.info(f"Linking Google account to existing user {email}")
                user.auth_provider = AuthProvider.GOOGLE.value
                user.provider_user_id = google_id
                user.provider_email = email
                user.avatar_url = picture
                user.email_verified = verified_email
                user.oauth_access_token = encrypted_access
                user.oauth_refresh_token = encrypted_refresh
                user.provider_data = user_info
                user.last_login = datetime.utcnow()
                db.commit()
                db.refresh(user)
            elif current_provider == google_value:
                # Update OAuth tokens for existing Google user
                logger.info(f"Updating OAuth tokens for existing Google user {email}")
                user.oauth_access_token = encrypted_access
                user.oauth_refresh_token = encrypted_refresh
                user.avatar_url = picture
                user.email_verified = verified_email
                user.provider_data = user_info
                user.last_login = datetime.utcnow()
                db.commit()
                db.refresh(user)
            else:
                # Fallback: if user has password, treat as password auth and link Google
                if user.hashed_password:
                    logger.warning(f"User {email} has unexpected auth_provider '{user.auth_provider}' but has password - linking Google account")
                    user.auth_provider = AuthProvider.GOOGLE.value
                    user.provider_user_id = google_id
                    user.provider_email = email
                    user.avatar_url = picture
                    user.email_verified = verified_email
                    user.oauth_access_token = encrypted_access
                    user.oauth_refresh_token = encrypted_refresh
                    user.provider_data = user_info
                    user.last_login = datetime.utcnow()
                    db.commit()
                    db.refresh(user)
                else:
                    logger.error(f"User {email} has unexpected auth_provider: '{user.auth_provider}'")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Account already exists with different provider: {user.auth_provider}"
                    )
        else:
            # New user - create account
            logger.info(f"Creating new user from Google OAuth: {email}")
            user = User(
                id=str(uuid.uuid4()),
                email=email,
                name=name,
                hashed_password=None,  # No password for OAuth users
                auth_provider=AuthProvider.GOOGLE.value,  # Use .value for string
                provider_user_id=google_id,
                provider_email=email,
                avatar_url=picture,
                email_verified=verified_email,
                oauth_access_token=encrypted_access,
                oauth_refresh_token=encrypted_refresh,
                provider_data=user_info,
                role="um_nurse",  # Default role
                is_active=True,
                created_at=datetime.utcnow(),
                last_login=datetime.utcnow(),
            )
            user = user_repository.create(db, user)
        
        # Create JWT token
        jwt_token = create_access_token(data={"sub": user.id})
        
        # Redirect to frontend with token in query parameter
        # Frontend will extract token from URL and store it
        from urllib.parse import urlencode
        
        frontend_url = settings.FRONTEND_URL
        
        # URL encode parameters to handle special characters
        params = {
            "token": jwt_token,
            "success": "true",
            "email": user.email,
            "name": user.name,
        }
        redirect_url = f"{frontend_url}/auth/google/callback?{urlencode(params)}"
        
        logger.info(f"Redirecting to frontend: {frontend_url}/auth/google/callback")
        
        return RedirectResponse(url=redirect_url)
        
    except Exception as e:
        logger.error(f"Error in Google OAuth callback: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OAuth authentication failed: {str(e)}"
        )
