"""Mesh authentication module.

Provides GitHub PAT-based authentication and tier detection.
"""

from mesh.auth.client import GitHubClient, GitHubUser, GitHubOrg, get_client
from mesh.auth.storage import AuthStorage, StoredAuth, get_storage
from mesh.auth.tier import (
    TierDetector,
    TierInfo,
    FREE_TIER,
    PERSONAL_PRO_TIER,
    ORG_PRO_TIER,
    ORG_PRO_DISCOUNT_TIER,
    TIER_FREE,
    TIER_PERSONAL_PRO,
    TIER_ORG_PRO,
    TIER_ORG_PRO_DISCOUNT,
    get_detector,
)

__all__ = [
    "GitHubClient",
    "GitHubUser",
    "GitHubOrg",
    "get_client",
    "AuthStorage",
    "StoredAuth",
    "get_storage",
    "TierDetector",
    "TierInfo",
    "FREE_TIER",
    "PERSONAL_PRO_TIER",
    "ORG_PRO_TIER",
    "ORG_PRO_DISCOUNT_TIER",
    "TIER_FREE",
    "TIER_PERSONAL_PRO",
    "TIER_ORG_PRO",
    "TIER_ORG_PRO_DISCOUNT",
    "get_detector",
]
