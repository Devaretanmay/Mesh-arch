"""API routes for user endpoints."""

from fastapi import APIRouter, Depends
from typing import List

router = APIRouter(prefix="/api/users", tags=["users"])


def getUserData(user_id: int):
    """Get user data - naming violation (should be get_user_data)."""
    return {"id": user_id}


def get_user_profile(user_id: int) -> dict:
    """Get user profile information."""
    return {"user_id": user_id, "profile": "data"}


@router.get("/")
def list_users() -> List[dict]:
    """List all users."""
    return []


@router.get("/{user_id}")
def get_user(user_id: int) -> dict:
    """Get a specific user."""
    return get_user_profile(user_id)
