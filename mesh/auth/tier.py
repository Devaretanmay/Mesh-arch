"""Tier detection and management for Mesh Pro subscriptions."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from mesh.auth.client import GitHubClient
from mesh.auth.storage import AuthStorage, StoredAuth

TIER_FREE = "free"
TIER_PRO = "pro"


@dataclass
class TierInfo:
    tier: str
    display_name: str
    features: list[str]


FREE_TIER = TierInfo(
    tier=TIER_FREE,
    display_name="Free",
    features=[
        "mesh init - Initialize codebase analysis",
        "mesh check - Check architectural violations",
        "mesh ask - AI-powered codebase queries",
        "mesh serve - MCP server for AI assistants",
        "All graph analysis features",
    ],
)

PRO_TIER = TierInfo(
    tier=TIER_PRO,
    display_name="Pro",
    features=[
        "All Free features",
        "Priority support",
    ],
)


class TierDetector:
    def __init__(self, client: GitHubClient, storage: AuthStorage):
        self.client = client
        self.storage = storage

    def detect_and_save(self, token: str) -> tuple[bool, str, str]:
        user = self.client.get_user(token)
        if not user:
            return False, "", "Failed to fetch user from GitHub"

        auth = StoredAuth(
            login=user.login,
            user_id=user.id,
            tier=TIER_PRO,
            orgs=[],
            orgs_with_members=[],
            validated_at=datetime.utcnow().isoformat(),
        )

        self.storage.save_token(token)
        self.storage.save_auth(auth)

        return True, TIER_PRO, f"Authenticated as {user.login}"

    def get_current_tier(self) -> TierInfo:
        auth = self.storage.get_auth()
        if not auth:
            return FREE_TIER
        return PRO_TIER

    def get_auth_info(self) -> Optional[StoredAuth]:
        return self.storage.get_auth()

    def is_pro_feature_allowed(self, feature: str) -> tuple[bool, str]:
        return True, "all_features_free"

    def logout(self) -> None:
        self.storage.clear_all()


def get_detector() -> TierDetector:
    return TierDetector(GitHubClient(), AuthStorage())
