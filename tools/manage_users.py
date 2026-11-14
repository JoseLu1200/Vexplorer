from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
from pathlib import Path


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
HASH_PATTERN = re.compile(
    r"^\$scrypt\$ln=(?P<ln>\d+),r=(?P<r>\d+),p=(?P<p>\d+)\$(?P<salt>[A-Za-z0-9_-]+)\$(?P<digest>[A-Za-z0-9_-]+)$"
)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    if not password or len(password.encode("utf-8")) > 1024:
        raise ValueError("invalid_password")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"$scrypt$ln=14,r=8,p=1${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    match = HASH_PATTERN.fullmatch(encoded)
    if match is None:
        return False
    try:
        ln, r, p = (int(match.group(name)) for name in ("ln", "r", "p"))
        if (ln, r, p) != (14, 8, 1):
            return False
        salt = _b64decode(match.group("salt"))
        expected = _b64decode(match.group("digest"))
        if len(salt) != 16 or len(expected) != 32:
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=2**ln, r=r, p=p, dklen=32
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def _validate_users(users: dict[str, str]) -> None:
    if not users:
        raise ValueError("empty_users")
    for username, encoded in users.items():
        if USERNAME_PATTERN.fullmatch(username) is None:
            raise ValueError("invalid_username")
        if HASH_PATTERN.fullmatch(encoded) is None:
            raise ValueError("invalid_password_hash")


def write_users_file(path: Path, users: dict[str, str]) -> None:
    _validate_users(users)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as output:
            json.dump(dict(sorted(users.items())), output, indent=2)
            output.write("\n")
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def read_users_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    ):
        raise ValueError("invalid_users_file")
    if value:
        _validate_users(value)
    return value


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        value = sys.stdin.readline()
        if value == "":
            raise ValueError("password_stdin_empty")
        return value.rstrip("\r\n")
    first = getpass.getpass("Password: ")
    second = getpass.getpass("Repeat password: ")
    if first != second:
        raise ValueError("password_mismatch")
    return first


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage named Vexplorer users without password argv.")
    parser.add_argument("--file", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    set_user = commands.add_parser("set")
    set_user.add_argument("username")
    set_user.add_argument("--password-stdin", action="store_true")
    delete = commands.add_parser("delete")
    delete.add_argument("username")
    commands.add_parser("list")
    return parser


def main() -> int:
    args = _parser().parse_args()
    users = read_users_file(args.file)
    if args.command == "list":
        for username in sorted(users):
            print(username)
        return 0
    if USERNAME_PATTERN.fullmatch(args.username) is None:
        raise ValueError("invalid_username")
    if args.command == "set":
        users[args.username] = hash_password(_read_password(args.password_stdin))
    else:
        if args.username not in users:
            raise ValueError("unknown_username")
        del users[args.username]
        if not users:
            raise ValueError("cannot_delete_last_user")
    write_users_file(args.file, users)
    print(args.username)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
