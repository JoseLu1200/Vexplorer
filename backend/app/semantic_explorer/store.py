from __future__ import annotations

import hashlib
import io
import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from PIL import Image

from .core import make_snapshot, public_entry, snapshot_id
from .models import Bundle, MAX_IMAGE_BYTES, digest


class ExplorerStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS releases(id TEXT PRIMARY KEY, catalog TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS active(catalog TEXT PRIMARY KEY, release_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS images(release_id TEXT, member_id TEXT, content BLOB NOT NULL, PRIMARY KEY(release_id,member_id));
                CREATE TABLE IF NOT EXISTS retired(catalog TEXT, member_id TEXT, PRIMARY KEY(catalog,member_id));
                CREATE TABLE IF NOT EXISTS projections(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reviews(id TEXT PRIMARY KEY, state TEXT NOT NULL, payload TEXT, day TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS audit(sequence INTEGER PRIMARY KEY, action TEXT NOT NULL, subject TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
            """)
            if "checksum" not in {
                r[1] for r in db.execute("PRAGMA table_info(projections)")
            }:
                db.execute(
                    "ALTER TABLE projections ADD COLUMN checksum TEXT NOT NULL DEFAULT ''"
                )

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute(
            "PRAGMA max_page_count=65536"
        )  # 256 MiB with SQLite's default pages.
        try:
            with db:
                yield db
        finally:
            db.close()

    def publish(self, catalog: str, bundle: Bundle, images: dict[str, bytes]) -> str:
        if re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", catalog) is None:
            raise ValueError("invalid_catalog")
        bundle = Bundle.model_validate(bundle.model_dump())
        if set(images) - {e.id for e in bundle.entries}:
            raise ValueError("image_member_unknown")
        entries = []
        for entry in sorted(bundle.entries, key=lambda e: e.id):
            data = images.get(entry.id)
            if data is not None:
                if len(data) > MAX_IMAGE_BYTES:
                    raise ValueError("image_too_large")
                try:
                    with Image.open(io.BytesIO(data)) as img:
                        if img.format != "PNG" or max(img.size) > 2048:
                            raise ValueError("invalid_image")
                        img.verify()
                except Exception as exc:
                    raise ValueError("invalid_image") from exc
                entry = entry.model_copy(
                    update={"image_hash": hashlib.sha256(data).hexdigest()}
                )
            elif entry.image_hash is not None:
                raise ValueError("image_missing")
            entries.append(entry)
        bundle = bundle.model_copy(update={"entries": tuple(entries)})
        payload = bundle.model_dump(mode="json")
        release = digest({"catalog": catalog, "bundle": payload})
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT OR IGNORE INTO releases VALUES (?,?,?)",
                (release, catalog, json.dumps(payload, allow_nan=False)),
            )
            for member, data in images.items():
                db.execute(
                    "INSERT OR IGNORE INTO images VALUES (?,?,?)",
                    (release, member, data),
                )
            db.execute(
                "INSERT INTO audit(action,subject) VALUES ('publish',?)", (release,)
            )
        return release

    @staticmethod
    def _read(db, catalog: str, release: str) -> Bundle:
        row = db.execute(
            "SELECT payload FROM releases WHERE id=? AND catalog=?", (release, catalog)
        ).fetchone()
        if row is None:
            raise KeyError(release)
        try:
            payload = json.loads(row[0])
            if digest({"catalog": catalog, "bundle": payload}) != release:
                raise ValueError("hash")
            return Bundle.model_validate(payload)
        except (ValueError, TypeError) as exc:
            raise ValueError("corrupt_release") from exc

    def activate(
        self, catalog: str, release: str, *, expected_release: str | None = None
    ) -> None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if expected_release is not None:
                current = db.execute(
                    "SELECT release_id FROM active WHERE catalog=?", (catalog,)
                ).fetchone()
                if current is None or current[0] != expected_release:
                    raise ValueError("active_release_changed")
            self._read(db, catalog, release)
            db.execute("INSERT OR REPLACE INTO active VALUES (?,?)", (catalog, release))
            db.execute(
                "INSERT INTO audit(action,subject) VALUES ('activate',?)", (release,)
            )

    def retire(self, catalog: str, member_id: str) -> None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT OR IGNORE INTO retired VALUES (?,?)", (catalog, member_id)
            )
            db.execute(
                "INSERT INTO audit(action,subject) VALUES ('retire',?)",
                (f"{catalog}:{member_id}",),
            )

    def catalogs(self) -> list[str]:
        with self.connect() as db:
            return [
                r[0] for r in db.execute("SELECT catalog FROM active ORDER BY catalog")
            ]

    def load(self, catalog: str) -> tuple[str, Bundle]:
        with self.connect() as db:
            db.execute("BEGIN")
            row = db.execute(
                "SELECT release_id FROM active WHERE catalog=?", (catalog,)
            ).fetchone()
            if row is None:
                raise KeyError(catalog)
            bundle = self._read(db, catalog, row[0])
            retired = {
                r[0]
                for r in db.execute(
                    "SELECT member_id FROM retired WHERE catalog=?", (catalog,)
                )
            }
            return row[0], bundle.model_copy(
                update={
                    "entries": tuple(e for e in bundle.entries if e.id not in retired)
                }
            )

    def image(self, catalog: str, member_id: str) -> bytes:
        release, bundle = self.load(catalog)
        entry = next((e for e in bundle.entries if e.id == member_id), None)
        if entry is None or entry.image_hash is None:
            raise KeyError(member_id)
        with self.connect() as db:
            row = db.execute(
                "SELECT content FROM images WHERE release_id=? AND member_id=?",
                (release, member_id),
            ).fetchone()
        if row is None or hashlib.sha256(row[0]).hexdigest() != entry.image_hash:
            raise ValueError("corrupt_image")
        return row[0]

    def active_images(self, catalog: str, expected_release: str) -> dict[str, bytes]:
        """Copy eligible images in one read transaction, without parsing N bundles."""
        with self.connect() as db:
            db.execute("BEGIN")
            active = db.execute(
                "SELECT release_id FROM active WHERE catalog=?", (catalog,)
            ).fetchone()
            if active is None or active[0] != expected_release:
                raise ValueError("active_release_changed")
            bundle = self._read(db, catalog, expected_release)
            retired = {
                r[0]
                for r in db.execute(
                    "SELECT member_id FROM retired WHERE catalog=?", (catalog,)
                )
            }
            stored = dict(
                db.execute(
                    "SELECT member_id,content FROM images WHERE release_id=?",
                    (expected_release,),
                )
            )
            result = {}
            for entry in bundle.entries:
                if entry.id in retired or entry.image_hash is None:
                    continue
                raw = stored.get(entry.id)
                if raw is None or hashlib.sha256(raw).hexdigest() != entry.image_hash:
                    raise ValueError("corrupt_image")
                result[entry.id] = raw
            return result

    def snapshot(self, bundle: Bundle, source: str) -> dict:
        identity = snapshot_id(bundle, source)
        with self.connect() as db:
            row = db.execute(
                "SELECT payload,checksum FROM projections WHERE id=?", (identity,)
            ).fetchone()
        if row is not None:
            try:
                cached = json.loads(row[0])
                metadata = [
                    {k: v for k, v in point.items() if k not in {"x", "y"}}
                    for point in cached["points"]
                ]
                if (
                    digest(cached) == row[1]
                    and cached["snapshot_id"] == identity
                    and cached["source"] == source
                    and cached["vector_space_id"] == bundle.space.id
                    and cached["space"] == bundle.space.model_dump(mode="json")
                    and metadata == [public_entry(entry) for entry in bundle.entries]
                ):
                    return cached
            except (ValueError, TypeError, KeyError, AttributeError):
                pass  # A derived cache is never an authority for membership.
        value = make_snapshot(bundle, source)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT OR REPLACE INTO projections(id,payload,checksum) VALUES (?,?,?)",
                (identity, json.dumps(value, allow_nan=False), digest(value)),
            )
            # Bounded cache, not an authority for catalog membership.
            db.execute(
                "DELETE FROM projections WHERE rowid NOT IN (SELECT rowid FROM projections ORDER BY rowid DESC LIMIT 32)"
            )
            return value
