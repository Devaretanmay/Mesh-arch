"""Secure token storage using OS keychain via keyring library."""

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import keyring

SERVICE_NAME = "mesh-arch"
KEYRING_FALLBACK_FILE = "~/.mesh/auth.json"


@dataclass
class StoredAuth:
    login: str
    user_id: int
    tier: str
    orgs: list[str]
    orgs_with_members: list[str]
    validated_at: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "StoredAuth":
        return cls(
            login=data.get("login", ""),
            user_id=data.get("user_id", 0),
            tier=data.get("tier", "free"),
            orgs=data.get("orgs", []),
            orgs_with_members=data.get("orgs_with_members", []),
            validated_at=data.get("validated_at", ""),
        )


class AuthStorage:
    def __init__(self):
        self._keyring_service = SERVICE_NAME
        self._token_key = f"{SERVICE_NAME}.token"

    def save_token(self, token: str) -> None:
        try:
            keyring.set_password(self._keyring_service, self._token_key, token)
        except keyring.errors.KeyringError:
            self._save_token_fallback(token)

    def get_token(self) -> Optional[str]:
        try:
            return keyring.get_password(self._keyring_service, self._token_key)
        except keyring.errors.KeyringError:
            return self._get_token_fallback()

    def delete_token(self) -> None:
        try:
            keyring.delete_password(self._keyring_service, self._token_key)
        except keyring.errors.KeyringError:
            pass
        self._delete_token_fallback()

    def save_auth(self, auth: StoredAuth) -> None:
        auth_path = self._auth_file_path()
        auth_path.parent.mkdir(parents=True, exist_ok=True)
        auth_path.write_text(json.dumps(auth.to_dict(), indent=2))

    def get_auth(self) -> Optional[StoredAuth]:
        auth_path = self._auth_file_path()
        if not auth_path.exists():
            return None
        try:
            data = json.loads(auth_path.read_text())
            return StoredAuth.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            return None

    def delete_auth(self) -> None:
        auth_path = self._auth_file_path()
        if auth_path.exists():
            auth_path.unlink()

    def clear_all(self) -> None:
        self.delete_token()
        self.delete_auth()

    def _auth_file_path(self) -> Path:
        return Path(KEYRING_FALLBACK_FILE).expanduser()

    def _save_token_fallback(self, token: str) -> None:
        auth_path = self._auth_file_path()
        auth_path.parent.mkdir(parents=True, exist_ok=True)
        mask = "ghp_****" + token[-4:] if len(token) > 4 else "****"
        auth_path.write_text(json.dumps({"token_hint": mask}))

    def _get_token_fallback(self) -> Optional[str]:
        return None

    def _delete_token_fallback(self) -> None:
        auth_path = self._auth_file_path()
        if auth_path.exists():
            auth_path.unlink()


def get_storage() -> AuthStorage:
    return AuthStorage()
