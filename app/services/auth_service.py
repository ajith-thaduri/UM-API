"""Authentication service for JWT and password handling"""

from datetime import datetime, timedelta
from typing import Optional
import hashlib
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.repositories.token_blacklist_repository import TokenBlacklistRepository

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Create repository instances
user_repository = UserRepository()
token_blacklist_repository = TokenBlacklistRepository()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    # Pre-hash plain password with SHA-256 to avoid bcrypt 72-byte limit
    try:
        password_hash = hashlib.sha256(plain_password.encode("utf-8")).hexdigest()
        return pwd_context.verify(password_hash, hashed_password)
    except Exception:
        # Fallback for existing passwords that might not be SHA-256 pre-hashed
        # or other verification errors
        return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password"""
    # Pre-hash password with SHA-256 to avoid bcrypt 72-byte limit
    password_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return pwd_context.hash(password_hash)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """Authenticate a user by email and password"""
    user = user_repository.get_by_email(db, email)
    if not user:
        return None
    if not user.is_active:
        return None
    if not user.hashed_password:
        return None  # User doesn't have a password set
    if not verify_password(password, user.hashed_password):
        return None
    
    # Update last login
    user.last_login = datetime.utcnow()
    db.commit()
    
    return user


def get_user_from_token(token: str, db: Session, allow_expired: bool = False) -> Optional[User]:
    """Get user from JWT token
    
    Args:
        token: JWT token string
        db: Database session
        allow_expired: If True, decode token even if expired (for refresh purposes)
    """
    # Check if token is blacklisted (unless we're allowing expired for refresh)
    if not allow_expired and token_blacklist_repository.is_blacklisted(db, token):
        return None
    
    try:
        if allow_expired:
            # Decode without verifying expiration
            payload = jwt.decode(
                token, 
                settings.SECRET_KEY, 
                algorithms=[settings.ALGORITHM],
                options={"verify_exp": False}
            )
        else:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
        
        # Get expiration time from token
        exp = payload.get("exp")
        expires_at = datetime.utcfromtimestamp(exp) if exp else None
    except JWTError:
        return None
    
    user = user_repository.get_by_id(db, user_id)
    if not user or not user.is_active:
        return None
    return user


def blacklist_token(token: str, db: Session) -> bool:
    """Add a token to the blacklist
    
    Args:
        token: JWT token string
        db: Database session
        
    Returns:
        True if token was blacklisted, False if token is invalid
    """
    try:
        # Decode token to get user_id and expiration
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_exp": False}  # Allow expired tokens to be blacklisted
        )
        
        user_id: str = payload.get("sub")
        exp = payload.get("exp")
        
        if user_id is None:
            return False
        
        # Get expiration time
        expires_at = datetime.utcfromtimestamp(exp) if exp else datetime.utcnow() + timedelta(days=7)
        
        # Add to blacklist
        token_blacklist_repository.add_token(db, token, user_id, expires_at)
        return True
    except JWTError:
        return False

