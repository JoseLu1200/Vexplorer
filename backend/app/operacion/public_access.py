"""Persistent admission control for unauthenticated public mutations."""
from __future__ import annotations

import hashlib
import hmac
import math
import secrets
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


PublicMutationAction = Literal["upload", "job", "other"]

_DAY_SECONDS = 86_400
_MINUTE_SECONDS = 60
_MAX_CONFIGURED_DAILY_LIMIT = 1_000_000
_MAX_CONFIGURED_MINUTE_LIMIT = 100_000
_MAX_CONTENT_LENGTH_BYTES = 100 * 1024 * 1024
_MIN_HASH_KEY_BYTES = 16


@dataclass(frozen=True, slots=True)
class PublicAdmissionLimits:
    global_uploads_daily: int = 100
    per_ip_uploads_daily: int = 20
    global_jobs_daily: int = 100
    per_ip_jobs_daily: int = 20
    per_ip_mutations_minute: int = 30
    max_content_length_bytes: int = 21 * 1024 * 1024
    cleanup_batch_size: int = 1_000


@dataclass(frozen=True, slots=True)
class PublicAdmissionDecision:
    allowed: bool
    status_code: int | None = None
    code: str | None = None
    retry_after_seconds: int | None = None


_ALLOWED = PublicAdmissionDecision(allowed=True)


class PublicAdmissionStore:
    """Atomically admit public mutations using the application's SQLite file."""

    def __init__(
        self,
        path: Path,
        *,
        limits: PublicAdmissionLimits | None = None,
        clock: Callable[[], float] = time.time,
        ip_hash_key: bytes | None = None,
    ) -> None:
        self.path = Path(path)
        self.limits = limits or PublicAdmissionLimits()
        self.clock = clock
        self._validate_limits(self.limits)
        if ip_hash_key is not None and len(ip_hash_key) < _MIN_HASH_KEY_BYTES:
            raise ValueError("invalid_ip_hash_key")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ip_hash_key = self._initialize_schema_and_key(ip_hash_key)

    @staticmethod
    def _validate_limits(limits: PublicAdmissionLimits) -> None:
        integer_values = (
            limits.global_uploads_daily,
            limits.per_ip_uploads_daily,
            limits.global_jobs_daily,
            limits.per_ip_jobs_daily,
            limits.per_ip_mutations_minute,
            limits.max_content_length_bytes,
            limits.cleanup_batch_size,
        )
        valid = (
            all(type(value) is int and value > 0 for value in integer_values)
            and limits.per_ip_uploads_daily <= limits.global_uploads_daily <= _MAX_CONFIGURED_DAILY_LIMIT
            and limits.per_ip_jobs_daily <= limits.global_jobs_daily <= _MAX_CONFIGURED_DAILY_LIMIT
            and limits.per_ip_mutations_minute <= _MAX_CONFIGURED_MINUTE_LIMIT
            and limits.max_content_length_bytes <= _MAX_CONTENT_LENGTH_BYTES
            and limits.cleanup_batch_size <= 10_000
        )
        if not valid:
            raise ValueError("invalid_public_admission_limits")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _initialize_schema_and_key(self, explicit_key: bytes | None) -> bytes:
        with self._connect() as database:
            database.executescript(
                """
                CREATE TABLE IF NOT EXISTS public_admission_metadata (
                    name TEXT PRIMARY KEY,
                    value BLOB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS public_admission_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    occurred_at REAL NOT NULL,
                    ip_hash TEXT NOT NULL CHECK(length(ip_hash) = 64),
                    action TEXT NOT NULL CHECK(action IN ('upload', 'job', 'other'))
                );
                CREATE INDEX IF NOT EXISTS public_admission_events_time
                    ON public_admission_events (occurred_at);
                CREATE INDEX IF NOT EXISTS public_admission_events_action_time
                    ON public_admission_events (action, occurred_at);
                CREATE INDEX IF NOT EXISTS public_admission_events_ip_time
                    ON public_admission_events (ip_hash, occurred_at);
                CREATE INDEX IF NOT EXISTS public_admission_events_ip_action_time
                    ON public_admission_events (ip_hash, action, occurred_at);
                """
            )
            candidate = explicit_key or secrets.token_bytes(32)
            database.execute("BEGIN IMMEDIATE")
            try:
                database.execute(
                    "INSERT OR IGNORE INTO public_admission_metadata (name, value) VALUES ('ip_hash_key', ?)",
                    (candidate,),
                )
                row = database.execute(
                    "SELECT value FROM public_admission_metadata WHERE name = 'ip_hash_key'"
                ).fetchone()
                database.commit()
            except Exception:
                database.rollback()
                raise
        if row is None:
            raise RuntimeError("public_admission_key_unavailable")
        stored = bytes(row[0])
        if len(stored) < _MIN_HASH_KEY_BYTES:
            raise ValueError("invalid_stored_ip_hash_key")
        if explicit_key is not None and not hmac.compare_digest(stored, explicit_key):
            raise ValueError("ip_hash_key_mismatch")
        return stored

    def admit_mutation(
        self,
        client_ip: str,
        action: PublicMutationAction,
        *,
        content_length: str | int | None = None,
        database: sqlite3.Connection | None = None,
    ) -> PublicAdmissionDecision:
        if action not in {"upload", "job", "other"}:
            raise ValueError("invalid_public_mutation_action")
        normalized_ip = client_ip.strip().casefold() if isinstance(client_ip, str) else ""
        if not normalized_ip or len(normalized_ip) > 255:
            raise ValueError("invalid_client_ip")
        if action == "upload":
            content_decision = self._check_content_length(content_length)
            if content_decision is not None:
                return content_decision
        now = float(self.clock())
        if not math.isfinite(now) or now < 0:
            raise ValueError("invalid_admission_clock")
        ip_hash = hmac.new(
            self._ip_hash_key,
            normalized_ip.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        owns_database = database is None
        active_database = database or self._connect()
        if not owns_database and not active_database.in_transaction:
            raise ValueError("public_admission_transaction_required")
        try:
            if owns_database:
                active_database.execute("BEGIN IMMEDIATE")
            self._cleanup_expired(active_database, now)
            decision = self._quota_decision(active_database, now, ip_hash, action)
            if decision.allowed:
                active_database.execute(
                    "INSERT INTO public_admission_events (occurred_at, ip_hash, action) VALUES (?, ?, ?)",
                    (now, ip_hash, action),
                )
            if owns_database:
                active_database.commit()
            return decision
        except Exception:
            if owns_database:
                active_database.rollback()
            raise
        finally:
            if owns_database:
                active_database.close()

    def _check_content_length(self, value: str | int | None) -> PublicAdmissionDecision | None:
        if value is None:
            return None
        if type(value) is int:
            parsed = value
        elif isinstance(value, str):
            digits = value.strip()
            if not digits or not digits.isascii() or not digits.isdigit():
                return PublicAdmissionDecision(False, 400, "invalid_content_length")
            normalized = digits.lstrip("0") or "0"
            if len(normalized) > 20:
                return PublicAdmissionDecision(False, 413, "upload_content_length_exceeded")
            parsed = int(normalized)
        else:
            return PublicAdmissionDecision(False, 400, "invalid_content_length")
        if parsed < 0:
            return PublicAdmissionDecision(False, 400, "invalid_content_length")
        if parsed > self.limits.max_content_length_bytes:
            return PublicAdmissionDecision(False, 413, "upload_content_length_exceeded")
        return None

    def _cleanup_expired(self, database: sqlite3.Connection, now: float) -> None:
        database.execute(
            """
            DELETE FROM public_admission_events
            WHERE id IN (
                SELECT id FROM public_admission_events
                WHERE occurred_at < ?
                ORDER BY occurred_at, id
                LIMIT ?
            )
            """,
            (now - _DAY_SECONDS, self.limits.cleanup_batch_size),
        )

    def _quota_decision(
        self,
        database: sqlite3.Connection,
        now: float,
        ip_hash: str,
        action: PublicMutationAction,
    ) -> PublicAdmissionDecision:
        minute = self._window_stats(
            database,
            "ip_hash = ? AND occurred_at > ?",
            (ip_hash, now - _MINUTE_SECONDS),
        )
        if minute[0] >= self.limits.per_ip_mutations_minute:
            return self._limited("public_mutation_rate_limited", minute[1], now, _MINUTE_SECONDS)
        if action == "other":
            return _ALLOWED

        global_limit = (
            self.limits.global_uploads_daily if action == "upload" else self.limits.global_jobs_daily
        )
        per_ip_limit = (
            self.limits.per_ip_uploads_daily if action == "upload" else self.limits.per_ip_jobs_daily
        )
        code = "public_upload_daily_limit" if action == "upload" else "public_job_daily_limit"
        global_daily = self._window_stats(
            database,
            "action = ? AND occurred_at > ?",
            (action, now - _DAY_SECONDS),
        )
        if global_daily[0] >= global_limit:
            return self._limited(code, global_daily[1], now, _DAY_SECONDS)
        client_daily = self._window_stats(
            database,
            "ip_hash = ? AND action = ? AND occurred_at > ?",
            (ip_hash, action, now - _DAY_SECONDS),
        )
        if client_daily[0] >= per_ip_limit:
            return self._limited(code, client_daily[1], now, _DAY_SECONDS)
        return _ALLOWED

    @staticmethod
    def _window_stats(
        database: sqlite3.Connection,
        where: str,
        parameters: tuple[object, ...],
    ) -> tuple[int, float | None]:
        row = database.execute(
            f"SELECT COUNT(*), MIN(occurred_at) FROM public_admission_events WHERE {where}",
            parameters,
        ).fetchone()
        return int(row[0]), None if row[1] is None else float(row[1])

    @staticmethod
    def _limited(
        code: str,
        oldest: float | None,
        now: float,
        window_seconds: int,
    ) -> PublicAdmissionDecision:
        if oldest is None:
            retry_after = window_seconds
        else:
            retry_after = max(1, min(window_seconds, math.ceil(oldest + window_seconds - now)))
        return PublicAdmissionDecision(False, 429, code, retry_after)
