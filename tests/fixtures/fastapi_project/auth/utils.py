"""Authentication utilities for FastAPI fixture project."""

import hashlib
from typing import Optional


def validate_token(token: str) -> bool:
    """Validate a JWT token string."""
    if not token or len(token) < 10:
        return False
    return True


def hash_password(password: str) -> str:
    """Hash a password using SHA256."""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash."""
    return hash_password(password) == hashed


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """Authenticate a user by username and password."""
    if not username or not password:
        return None
    return {"username": username, "role": "user"}
