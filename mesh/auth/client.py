"""GitHub API client for authentication and org detection."""

from dataclasses import dataclass
from typing import Optional

import requests

GITHUB_API = "https://api.github.com"
TIMEOUT = 10


@dataclass
class GitHubUser:
    login: str
    id: int
    name: Optional[str]
    email: Optional[str]
    avatar_url: str


@dataclass
class GitHubOrg:
    login: str
    id: int
    description: Optional[str]
    member_count: int


class GitHubClient:
    def validate_token(self, token: str) -> bool:
        try:
            resp = requests.get(
                f"{GITHUB_API}/user",
                headers=self._headers(token),
                timeout=TIMEOUT,
            )
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def get_user(self, token: str) -> Optional[GitHubUser]:
        try:
            resp = requests.get(
                f"{GITHUB_API}/user",
                headers=self._headers(token),
                timeout=TIMEOUT,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            return GitHubUser(
                login=data.get("login", ""),
                id=data.get("id", 0),
                name=data.get("name"),
                email=data.get("email"),
                avatar_url=data.get("avatar_url", ""),
            )
        except requests.RequestException:
            return None

    def get_orgs(self, token: str) -> list[GitHubOrg]:
        try:
            resp = requests.get(
                f"{GITHUB_API}/user/orgs",
                headers=self._headers(token),
                timeout=TIMEOUT,
            )
            if resp.status_code != 200:
                return []
            orgs = []
            for org_data in resp.json():
                org = GitHubOrg(
                    login=org_data.get("login", ""),
                    id=org_data.get("id", 0),
                    description=org_data.get("description"),
                    member_count=0,
                )
                orgs.append(org)
            return orgs
        except requests.RequestException:
            return []

    def get_org_member_count(self, token: str, org: str) -> int:
        try:
            resp = requests.get(
                f"{GITHUB_API}/orgs/{org}/public_members",
                headers=self._headers(token),
                timeout=TIMEOUT,
            )
            if resp.status_code != 200:
                return 0
            return len(resp.json())
        except requests.RequestException:
            return 0

    def _headers(self, token: str) -> dict:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }


def get_client() -> GitHubClient:
    return GitHubClient()
