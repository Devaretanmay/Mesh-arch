"""Authentication middleware."""

from auth.utils import validate_token


def validate_token(token: str) -> bool:
    """Validate token in middleware context."""
    if not token:
        return False
    return len(token) > 5


def get_current_user(request):
    """Get current user from request."""
    token = request.headers.get("Authorization", "")
    if validate_token(token):
        return {"id": 1, "name": "test_user"}
    return None


def require_auth(handler):
    """Decorator to require authentication."""

    def wrapper(request):
        if not get_current_user(request):
            return {"error": "Unauthorized"}
        return handler(request)

    return wrapper


def checkAuth(request):
    """Check authentication - camelCase violation."""
    return get_current_user(request)


def getUserData(userId):
    """Get user data - camelCase violation."""
    return {"id": userId, "name": "test"}


def updateProfile(userId, data):
    """Update profile - camelCase violation."""
    return {"status": "success"}


def isAuthenticated(token):
    """Check if authenticated - camelCase violation."""
    return validate_token(token)


def createSession(userId):
    """Create session - camelCase violation."""
    return {"session_id": "abc123", "user_id": userId}


def destroySession(sessionId):
    """Destroy session - camelCase violation."""
    return True


def getSessionInfo(sessionId):
    """Get session info - camelCase violation."""
    return {"id": sessionId}


def refreshSession(sessionId):
    """Refresh session - camelCase violation."""
    return {"session_id": sessionId}


def validateSession(sessionId):
    """Validate session - camelCase violation."""
    return True
