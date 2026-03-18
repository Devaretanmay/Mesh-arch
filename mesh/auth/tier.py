"""Tier detection and management for Mesh Pro subscriptions."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from mesh.auth.client import GitHubClient
from mesh.auth.storage import AuthStorage, StoredAuth

TIER_FREE = "free"
TIER_PERSONAL_PRO = "personal_pro"
TIER_ORG_PRO = "org_pro"
TIER_ORG_PRO_DISCOUNT = "org_pro_discount"

ORG_MEMBER_THRESHOLD = 1


@dataclass
class TierInfo:
    tier: str
    display_name: str
    features: list[str]
    requires_pro: bool


FREE_TIER = TierInfo(
    tier=TIER_FREE,
    display_name="Free",
    features=[
        "mesh init - Initialize codebase analysis",
        "mesh check - Check architectural violations",
        "mesh install-hook - Git pre-commit hook",
        "Basic graph queries (callers, callees)",
    ],
    requires_pro=False,
)

PERSONAL_PRO_TIER = TierInfo(
    tier=TIER_PERSONAL_PRO,
    display_name="Personal Pro ($5/mo)",
    features=[
        "All Free features",
        "mesh ask - AI-powered codebase queries",
        "Summary reports with AI insights",
        "Advanced MCP tools (dependencies, impact)",
    ],
    requires_pro=True,
)

ORG_PRO_TIER = TierInfo(
    tier=TIER_ORG_PRO,
    display_name="Organization Pro ($10/mo)",
    features=[
        "All Personal Pro features",
        "Team-wide analysis",
        "Organization dashboard",
        "Admin controls",
    ],
    requires_pro=True,
)

ORG_PRO_DISCOUNT_TIER = TierInfo(
    tier=TIER_ORG_PRO_DISCOUNT,
    display_name="Organization Pro ($7/mo)",
    features=[
        "All Personal Pro features",
        "Team-wide analysis (discounted rate)",
        "Organization dashboard",
        "Admin controls",
    ],
    requires_pro=True,
)

TIER_INFO = {
    TIER_FREE: FREE_TIER,
    TIER_PERSONAL_PRO: PERSONAL_PRO_TIER,
    TIER_ORG_PRO: ORG_PRO_TIER,
    TIER_ORG_PRO_DISCOUNT: ORG_PRO_DISCOUNT_TIER,
}


class TierDetector:
    def __init__(self, client: GitHubClient, storage: AuthStorage):
        self.client = client
        self.storage = storage

    def detect_and_save(self, token: str) -> tuple[bool, str, str]:
        user = self.client.get_user(token)
        if not user:
            return False, "", "Failed to fetch user from GitHub"

        orgs = self.client.get_orgs(token)
        orgs_with_members = []

        for org in orgs:
            member_count = self.client.get_org_member_count(token, org.login)
            if member_count > ORG_MEMBER_THRESHOLD:
                orgs_with_members.append(org.login)

        tier = TIER_FREE

        auth = StoredAuth(
            login=user.login,
            user_id=user.id,
            tier=tier,
            orgs=[o.login for o in orgs],
            orgs_with_members=orgs_with_members,
            validated_at=datetime.utcnow().isoformat(),
        )

        self.storage.save_token(token)
        self.storage.save_auth(auth)

        return True, tier, f"Authenticated as {user.login}"

    def get_current_tier(self) -> Optional[TierInfo]:
        auth = self.storage.get_auth()
        if not auth:
            return FREE_TIER
        return TIER_INFO.get(auth.tier, FREE_TIER)

    def get_auth_info(self) -> Optional[StoredAuth]:
        return self.storage.get_auth()

    def is_org_user(self) -> bool:
        auth = self.storage.get_auth()
        if not auth:
            return False
        return len(auth.orgs_with_members) > 0

    def is_pro_feature_allowed(self, feature_tier: str) -> tuple[bool, str]:
        auth = self.storage.get_auth()

        if not auth:
            return True, "free"

        if self.is_org_user() and auth.tier == TIER_FREE:
            orgs = ", ".join(auth.orgs_with_members)
            return False, f"org_upgrade:{orgs}"

        if auth.tier == TIER_FREE:
            return True, "free_personal"

        if auth.tier == TIER_PERSONAL_PRO:
            return True, "personal_pro"

        if auth.tier in (TIER_ORG_PRO, TIER_ORG_PRO_DISCOUNT):
            return True, "org_pro"

        return True, "free_personal"

    def logout(self) -> None:
        self.storage.clear_all()

    def upgrade(self, tier: str) -> bool:
        auth = self.storage.get_auth()
        if not auth:
            return False

        if tier == "personal_pro":
            new_tier = TIER_PERSONAL_PRO
        elif tier == "org_pro":
            new_tier = TIER_ORG_PRO
        elif tier == "org_pro_discount":
            new_tier = TIER_ORG_PRO_DISCOUNT
        else:
            return False

        auth.tier = new_tier
        self.storage.save_auth(auth)
        return True


def get_detector() -> TierDetector:
    return TierDetector(GitHubClient(), AuthStorage())
