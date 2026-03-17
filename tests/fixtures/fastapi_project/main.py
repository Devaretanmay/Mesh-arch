"""FastAPI fixture project for testing Mesh MCP tools."""

from fastapi import FastAPI, Depends, HTTPException
from typing import Optional

app = FastAPI()


def verify_token(token: str) -> dict:
    """Verify JWT token and return user info."""
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    return {"user_id": 1, "role": "admin"}


def get_current_user(token: str = Depends(verify_token)) -> dict:
    """Get current authenticated user."""
    return token


@app.get("/users/{user_id}")
def get_user(user_id: int, current_user: dict = Depends(get_current_user)):
    """Get user by ID - requires authentication."""
    return {"id": user_id, "name": "Test User"}


@app.get("/public")
def public_endpoint():
    """Public endpoint - no auth required."""
    return {"message": "Public data"}
