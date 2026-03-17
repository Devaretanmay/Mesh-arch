"""User repository for database operations."""

from typing import Optional, List


class UserRepository:
    """Repository for user database operations."""

    def __init__(self):
        self._users = {}

    def get_by_id(self, user_id: int) -> Optional[dict]:
        """Get user by ID."""
        return self._users.get(user_id)

    def get_all(self) -> List[dict]:
        """Get all users."""
        return list(self._users.values())

    def create(self, user_data: dict) -> int:
        """Create a new user."""
        user_id = len(self._users) + 1
        self._users[user_id] = user_data
        return user_id

    def update(self, user_id: int, user_data: dict) -> bool:
        """Update an existing user."""
        if user_id not in self._users:
            return False
        self._users[user_id] = user_data
        return True
