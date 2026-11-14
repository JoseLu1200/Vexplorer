from __future__ import annotations
import sqlite3
from contextlib import closing
from pathlib import Path
from backend.app.contratos.modelos import (
    GeneralDerivedPackage,
    GeneralFurnitureDraft,
    GeneralFurnitureProposal,
    GeneralFurnitureRecord,
    GeneralFurnitureReview,
)


class GeneralFurnitureRepository:
    def __init__(
        self,
        path: str | Path,
        *,
        max_proposals_per_run: int = 100,
        max_reviews_per_proposal: int = 100,
        max_database_bytes: int = 256 * 1024 * 1024,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_proposals_per_run = max_proposals_per_run
        self.max_reviews_per_proposal = max_reviews_per_proposal
        self.max_database_bytes = max_database_bytes
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS general_proposals(run_id TEXT NOT NULL,proposal_revision INTEGER NOT NULL,proposal_json TEXT NOT NULL,draft_json TEXT NOT NULL,PRIMARY KEY(run_id,proposal_revision))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS general_reviews(run_id TEXT NOT NULL,proposal_revision INTEGER NOT NULL,review_revision INTEGER NOT NULL,review_json TEXT NOT NULL,derived_json TEXT NOT NULL,PRIMARY KEY(run_id,proposal_revision,review_revision),FOREIGN KEY(run_id,proposal_revision) REFERENCES general_proposals(run_id,proposal_revision))"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def save_proposal(
        self,
        run_id: str,
        proposal: GeneralFurnitureProposal,
        draft: GeneralFurnitureDraft,
        *,
        base_proposal_revision: int,
    ) -> int:
        self._check_size_quota()
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            current = int(
                connection.execute(
                    "SELECT COALESCE(MAX(proposal_revision),0) FROM general_proposals WHERE run_id=?",
                    (run_id,),
                ).fetchone()[0]
            )
            if current != base_proposal_revision:
                raise ValueError("general_furniture_proposal_revision_conflict")
            if current >= self.max_proposals_per_run:
                raise ValueError("general_furniture_proposal_quota_exceeded")
            revision = current + 1
            connection.execute(
                "INSERT INTO general_proposals VALUES(?,?,?,?)",
                (run_id, revision, proposal.model_dump_json(), draft.model_dump_json()),
            )
        return revision

    def save_review(
        self,
        run_id: str,
        review: GeneralFurnitureReview,
        derived: GeneralDerivedPackage,
    ) -> None:
        if (
            review.run_id != run_id
            or derived.run_id != run_id
            or derived.proposal_revision != review.proposal_revision
            or derived.review_revision != review.review_revision
        ):
            raise ValueError("general_derived_revision_mismatch")
        if derived.construction is not None:
            expected_basis = (
                f"run:{run_id}:proposal:{review.proposal_revision}:"
                f"review:{review.review_revision}:scenario:"
                f"{review.construction_scenario_id}"
            )
            construction = derived.construction
            if (
                construction.run_id != run_id
                or construction.proposal_revision != review.proposal_revision
                or construction.review_revision != review.review_revision
                or construction.scenario_id != review.construction_scenario_id
                or construction.basis_revision != expected_basis
            ):
                raise ValueError("general_construction_snapshot_revision_mismatch")
        self._check_size_quota()
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            current = int(
                connection.execute(
                    "SELECT COALESCE(MAX(review_revision),0) FROM general_reviews WHERE run_id=? AND proposal_revision=?",
                    (run_id, review.proposal_revision),
                ).fetchone()[0]
            )
            if current != review.review_revision - 1:
                raise ValueError("general_furniture_revision_conflict")
            if current >= self.max_reviews_per_proposal:
                raise ValueError("general_furniture_review_quota_exceeded")
            connection.execute(
                "INSERT INTO general_reviews VALUES(?,?,?,?,?)",
                (
                    run_id,
                    review.proposal_revision,
                    review.review_revision,
                    review.model_dump_json(),
                    derived.model_dump_json(),
                ),
            )

    def get(
        self,
        run_id: str,
        *,
        proposal_revision: int | None = None,
        review_revision: int | None = None,
    ) -> GeneralFurnitureRecord | None:
        with closing(self._connect()) as connection:
            query = "SELECT proposal_revision,proposal_json,draft_json FROM general_proposals WHERE run_id=?"
            params: tuple[object, ...] = (run_id,)
            if proposal_revision is None:
                query += " ORDER BY proposal_revision DESC LIMIT 1"
            else:
                query += " AND proposal_revision=?"
                params += (proposal_revision,)
            proposal = connection.execute(query, params).fetchone()
            if proposal is None:
                return None
            resolved = int(proposal[0])
            query = "SELECT review_revision,review_json FROM general_reviews WHERE run_id=? AND proposal_revision=?"
            params = (run_id, resolved)
            if review_revision is None:
                query += " ORDER BY review_revision DESC LIMIT 1"
            else:
                query += " AND review_revision=?"
                params += (review_revision,)
            review_row = connection.execute(query, params).fetchone()
        review = (
            GeneralFurnitureReview.model_validate_json(review_row[1])
            if review_row
            else None
        )
        return GeneralFurnitureRecord(
            run_id=run_id,
            status=review.status if review else "needs_review",
            proposal_revision=resolved,
            review_revision=int(review_row[0]) if review_row else 0,
            proposal=GeneralFurnitureProposal.model_validate_json(proposal[1]),
            draft=GeneralFurnitureDraft.model_validate_json(proposal[2]),
            review=review,
        )

    def get_derived(
        self,
        run_id: str,
        *,
        proposal_revision: int | None = None,
        review_revision: int | None = None,
    ) -> GeneralDerivedPackage | None:
        record = self.get(
            run_id, proposal_revision=proposal_revision, review_revision=review_revision
        )
        if record is None or record.review_revision == 0:
            return None
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT derived_json FROM general_reviews WHERE run_id=? AND proposal_revision=? AND review_revision=?",
                (run_id, record.proposal_revision, record.review_revision),
            ).fetchone()
        return GeneralDerivedPackage.model_validate_json(row[0]) if row else None

    def _check_size_quota(self) -> None:
        size = sum(
            path.stat().st_size
            for path in (self.path, Path(str(self.path) + "-wal"))
            if path.exists()
        )
        if size >= self.max_database_bytes:
            raise ValueError("general_furniture_storage_quota_exceeded")
