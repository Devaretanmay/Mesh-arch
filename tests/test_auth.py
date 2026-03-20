"""Tests for Mesh authentication module.

Tests:
- GitHub API client
- Auth storage
- Tier detection
"""

from unittest.mock import Mock, patch

from mesh.auth.tier import (
    TierDetector,
    TIER_FREE,
    TIER_PRO,
)
from mesh.auth.storage import StoredAuth


class TestGitHubClient:
    """Tests for GitHub API client."""

    @patch("mesh.auth.client.requests.get")
    def test_validate_token_success(self, mock_get):
        """Test token validation with valid token."""
        from mesh.auth.client import GitHubClient

        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        client = GitHubClient()
        result = client.validate_token("ghp_test_token")

        assert result is True
        mock_get.assert_called_once()

    @patch("mesh.auth.client.requests.get")
    def test_validate_token_failure(self, mock_get):
        """Test token validation with invalid token."""
        from mesh.auth.client import GitHubClient

        mock_response = Mock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        client = GitHubClient()
        result = client.validate_token("invalid_token")

        assert result is False

    @patch("mesh.auth.client.requests.get")
    def test_get_user_success(self, mock_get):
        """Test fetching user data."""
        from mesh.auth.client import GitHubClient

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "login": "testuser",
            "id": 12345,
            "name": "Test User",
            "email": "test@example.com",
            "avatar_url": "https://example.com/avatar.png",
        }
        mock_get.return_value = mock_response

        client = GitHubClient()
        user = client.get_user("ghp_test_token")

        assert user is not None
        assert user.login == "testuser"
        assert user.id == 12345
        assert user.name == "Test User"

    @patch("mesh.auth.client.requests.get")
    def test_get_orgs(self, mock_get):
        """Test fetching user organizations."""
        from mesh.auth.client import GitHubClient

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"login": "org1", "id": 1, "description": "Org 1"},
            {"login": "org2", "id": 2, "description": "Org 2"},
        ]
        mock_get.return_value = mock_response

        client = GitHubClient()
        orgs = client.get_orgs("ghp_test_token")

        assert len(orgs) == 2
        assert orgs[0].login == "org1"
        assert orgs[1].login == "org2"


class TestStoredAuth:
    """Tests for StoredAuth dataclass."""

    def test_to_dict(self):
        """Test converting StoredAuth to dict."""
        auth = StoredAuth(
            login="testuser",
            user_id=123,
            tier=TIER_FREE,
            orgs=["org1"],
            orgs_with_members=["org1"],
            validated_at="2024-01-01T00:00:00",
        )

        data = auth.to_dict()

        assert data["login"] == "testuser"
        assert data["user_id"] == 123
        assert data["tier"] == TIER_FREE

    def test_from_dict(self):
        """Test creating StoredAuth from dict."""
        data = {
            "login": "testuser",
            "user_id": 123,
            "tier": TIER_FREE,
            "orgs": ["org1"],
            "orgs_with_members": [],
            "validated_at": "2024-01-01T00:00:00",
        }

        auth = StoredAuth.from_dict(data)

        assert auth.login == "testuser"
        assert auth.user_id == 123
        assert auth.tier == TIER_FREE


class TestTierDetector:
    """Tests for tier detection logic."""

    def test_free_tier_no_auth(self):
        """Test that no auth returns free tier."""
        mock_storage = Mock()
        mock_storage.get_auth.return_value = None

        mock_client = Mock()

        detector = TierDetector(mock_client, mock_storage)
        tier = detector.get_current_tier()

        assert tier.tier == TIER_FREE
        assert tier.display_name == "Free"

    def test_pro_tier_with_auth(self):
        """Test that authenticated user gets Pro tier."""
        mock_storage = Mock()
        mock_storage.get_auth.return_value = StoredAuth(
            login="testuser",
            user_id=123,
            tier=TIER_PRO,
            orgs=[],
            orgs_with_members=[],
            validated_at="2024-01-01T00:00:00",
        )

        mock_client = Mock()

        detector = TierDetector(mock_client, mock_storage)
        tier = detector.get_current_tier()

        assert tier.tier == TIER_PRO
        assert tier.display_name == "Pro"

    def test_all_features_free(self):
        """Test that all features are allowed for everyone."""
        mock_storage = Mock()
        mock_storage.get_auth.return_value = None

        mock_client = Mock()

        detector = TierDetector(mock_client, mock_storage)
        allowed, reason = detector.is_pro_feature_allowed("ask")

        assert allowed is True
        assert reason == "all_features_free"

    def test_logout(self):
        """Test logout clears storage."""
        mock_storage = Mock()
        mock_client = Mock()

        detector = TierDetector(mock_client, mock_storage)
        detector.logout()

        mock_storage.clear_all.assert_called_once()
