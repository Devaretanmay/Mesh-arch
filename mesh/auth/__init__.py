"""Mesh authentication module.

Provides GitHub PAT-based authentication.
"""

from mesh.auth.client import GitHubClient, GitHubUser, GitHubOrg, get_client
from mesh.auth.storage import AuthStorage, StoredAuth, get_storage
from mesh.auth.tier import (
    TierDetector,
    TierInfo,
    FREE_TIER,
    PRO_TIER,
    TIER_FREE,
    TIER_PRO,
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
    "PRO_TIER",
    "TIER_FREE",
    "TIER_PRO",
    "get_detector",
]
