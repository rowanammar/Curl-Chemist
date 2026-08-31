import os
import jwt
from datetime import datetime, timedelta
import bcrypt
from fastapi import HTTPException, status
from config import IS_DEV

# Secret key for JWT signing. Fallback to a dev key if not set.
JWT_SECRET = os.getenv("JWT_SECRET", "dev_secret_key" if IS_DEV else "")
if not JWT_SECRET:
    raise ValueError("JWT_SECRET must be set in production")

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

def hash_password(password: str) -> str:
    """Hashes a password using bcrypt."""
    # Truncate strictly to 71 bytes (bcrypt limit is 72 including null terminator)
    trunc_pass = password.encode('utf-8')[:71]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(trunc_pass, salt).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against its hashed version."""
    trunc_pass = plain_password.encode('utf-8')[:71]
    try:
        return bcrypt.checkpw(trunc_pass, hashed_password.encode('utf-8'))
    except Exception:
        return False

def create_access_token(username: str) -> str:
    """Creates a JWT access token valid for 24 hours."""
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode = {"sub": username, "exp": expire}
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> dict:
    """Decodes and validates a JWT access token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
