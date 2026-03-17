"""User service for business logic."""

from typing import Optional, List
from ..repositories.user_repository import UserRepository


class UserService:
    """Service for user business logic."""

    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    def get_user(self, user_id: int) -> Optional[dict]:
        """Get user by ID with business logic."""
        user = self.user_repo.get_by_id(user_id)
        if user:
            user["is_active"] = True
        return user

    def get_all_users(self) -> List[dict]:
        """Get all users with business logic."""
        return self.user_repo.get_all()

    def create_user(self, username: str, email: str) -> int:
        """Create a new user with validation."""
        if not username or not email:
            raise ValueError("Username and email are required")
        return self.user_repo.create(
            {
                "username": username,
                "email": email,
            }
        )
