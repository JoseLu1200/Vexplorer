from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
from dataclasses import dataclass
from pathlib import Path


USERNAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_PARAMETERS = (14, 8, 1)


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("invalid_scrypt_hash")
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _parse(encoded: str) -> tuple[int, int, int, bytes, bytes]:
    parts = encoded.split("$")
    if len(parts) != 5 or parts[:2] != ["", "scrypt"]:
        raise ValueError("invalid_scrypt_hash")
    parameters: dict[str, int] = {}
    try:
        for item in parts[2].split(","):
            key, value = item.split("=", 1)
            parameters[key] = int(value)
        values = (parameters["ln"], parameters["r"], parameters["p"])
        salt, digest = _decode(parts[3]), _decode(parts[4])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid_scrypt_hash") from exc
    if values != _PARAMETERS or len(salt) != 16 or len(digest) != 32:
        raise ValueError("invalid_scrypt_hash")
    return (*values, salt, digest)


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    if not password or len(password.encode("utf-8")) > 1024:
        raise ValueError("invalid_password")
    salt = salt or secrets.token_bytes(16)
    if len(salt) != 16:
        raise ValueError("invalid_salt")
    ln, r, p = _PARAMETERS
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=2**ln, r=r, p=p, dklen=32
    )
    return f"$scrypt$ln={ln},r={r},p={p}${_encode(salt)}${_encode(digest)}"


@dataclass(frozen=True)
class PasswordFile:
    users: dict[str, str]

    @classmethod
    def load(cls, path: Path) -> "PasswordFile":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("users_file_invalid") from exc
        if not isinstance(payload, dict) or not payload:
            raise ValueError("users_file_empty")
        users: dict[str, str] = {}
        for username, encoded in payload.items():
            if not isinstance(username, str) or USERNAME_PATTERN.fullmatch(username) is None:
                raise ValueError("invalid_username")
            if not isinstance(encoded, str):
                raise ValueError("invalid_scrypt_hash")
            _parse(encoded)
            users[username] = encoded
        return cls(users)

    def authenticate(self, username: str, password: str) -> str | None:
        encoded = self.users.get(username)
        if encoded is None or len(password.encode("utf-8")) > 1024:
            return None
        ln, r, p, salt, expected = _parse(encoded)
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=2**ln, r=r, p=p, dklen=32
        )
        return username if hmac.compare_digest(actual, expected) else None


def decode_basic_authorization(value: str | None) -> tuple[str, str] | None:
    if not value or not value.startswith("Basic "):
        return None
    try:
        raw = base64.b64decode(value[6:], validate=True).decode("utf-8")
        username, password = raw.split(":", 1)
    except (ValueError, UnicodeError):
        return None
    if USERNAME_PATTERN.fullmatch(username) is None:
        return None
    return username, password
