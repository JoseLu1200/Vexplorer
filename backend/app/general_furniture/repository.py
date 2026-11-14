from __future__ import annotations
import sqlite3
from contextlib import closing
from pathlib import Path
from backend.app.contratos.modelos import (
    GeneralAssemblyAttempt,
    GeneralAssemblyState,
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
        max_assembly_attempts_per_review: int = 100,
        max_database_bytes: int = 256 * 1024 * 1024,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_proposals_per_run = max_proposals_per_run
        self.max_reviews_per_proposal = max_reviews_per_proposal
        self.max_assembly_attempts_per_review = max_assembly_attempts_per_review
        self.max_database_bytes = max_database_bytes
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS general_proposals(run_id TEXT NOT NULL,proposal_revision INTEGER NOT NULL,proposal_json TEXT NOT NULL,draft_json TEXT NOT NULL,PRIMARY KEY(run_id,proposal_revision))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS general_reviews(run_id TEXT NOT NULL,proposal_revision INTEGER NOT NULL,review_revision INTEGER NOT NULL,review_json TEXT NOT NULL,derived_json TEXT NOT NULL,PRIMARY KEY(run_id,proposal_revision,review_revision),FOREIGN KEY(run_id,proposal_revision) REFERENCES general_proposals(run_id,proposal_revision))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS general_assembly_attempts(run_id TEXT NOT NULL,proposal_revision INTEGER NOT NULL,review_revision INTEGER NOT NULL,assembly_revision INTEGER NOT NULL,attempt_json TEXT NOT NULL,PRIMARY KEY(run_id,proposal_revision,review_revision,assembly_revision),FOREIGN KEY(run_id,proposal_revision,review_revision) REFERENCES general_reviews(run_id,proposal_revision,review_revision))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS general_assembly_cancellations(job_id TEXT PRIMARY KEY,run_id TEXT NOT NULL,requested_at TEXT NOT NULL)"
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
        package = GeneralDerivedPackage.model_validate_json(row[0]) if row else None
        if package is None:
            return None
        attempt = self.get_assembly_attempt(
            run_id,
            proposal_revision=record.proposal_revision,
            review_revision=record.review_revision,
        )
        if (
            attempt is not None
            and attempt.report.status == "accepted"
            and attempt.report.scene is not None
        ):
            state = self.get_assembly_state(
                run_id,
                proposal_revision=record.proposal_revision,
                review_revision=record.review_revision,
            )
            scene = attempt.report.scene
            if state is not None and state.ambiguous:
                scene = scene.model_copy(update={
                    "warnings": tuple(dict.fromkeys((
                        *scene.warnings,
                        "multiple_compatible_assembly_hypotheses",
                    )))
                })
            return package.model_copy(update={"scene": scene})
        return package

    def save_assembly_attempt(
        self,
        run_id: str,
        attempt: GeneralAssemblyAttempt,
        *,
        base_assembly_revision: int,
        cancellation_job_id: str | None = None,
    ) -> int:
        self._check_size_quota()
        if attempt.run_id != run_id:
            raise ValueError("general_assembly_run_mismatch")
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            latest_proposal = int(connection.execute(
                "SELECT COALESCE(MAX(proposal_revision),0) FROM general_proposals WHERE run_id=?",
                (run_id,),
            ).fetchone()[0])
            latest_review = int(connection.execute(
                "SELECT COALESCE(MAX(review_revision),0) FROM general_reviews WHERE run_id=? AND proposal_revision=?",
                (run_id, latest_proposal),
            ).fetchone()[0])
            if (
                attempt.proposal_revision != latest_proposal
                or attempt.review_revision != latest_review
                or latest_review == 0
            ):
                raise ValueError("general_assembly_revision_conflict")
            current = int(connection.execute(
                "SELECT COALESCE(MAX(assembly_revision),0) FROM general_assembly_attempts WHERE run_id=? AND proposal_revision=? AND review_revision=?",
                (run_id, latest_proposal, latest_review),
            ).fetchone()[0])
            if (
                current != base_assembly_revision
                or attempt.assembly_revision != current + 1
            ):
                raise ValueError("general_assembly_revision_conflict")
            if cancellation_job_id is not None and attempt.report.status == "accepted":
                cancelled = connection.execute(
                    "SELECT 1 FROM general_assembly_cancellations WHERE job_id=? AND run_id=?",
                    (cancellation_job_id, run_id),
                ).fetchone()
                if cancelled is not None:
                    raise ValueError("assembly_cancelled")
            if current >= self.max_assembly_attempts_per_review:
                raise ValueError("general_assembly_attempt_quota_exceeded")
            connection.execute(
                "INSERT INTO general_assembly_attempts VALUES(?,?,?,?,?)",
                (
                    run_id, latest_proposal, latest_review,
                    attempt.assembly_revision, attempt.model_dump_json(),
                ),
            )
        return attempt.assembly_revision

    def get_assembly_attempt(
        self,
        run_id: str,
        *,
        proposal_revision: int,
        review_revision: int,
        assembly_revision: int | None = None,
    ) -> GeneralAssemblyAttempt | None:
        query = (
            "SELECT attempt_json FROM general_assembly_attempts "
            "WHERE run_id=? AND proposal_revision=? AND review_revision=?"
        )
        params: tuple[object, ...] = (run_id, proposal_revision, review_revision)
        if assembly_revision is None:
            query += " ORDER BY assembly_revision DESC LIMIT 1"
        else:
            query += " AND assembly_revision=?"
            params += (assembly_revision,)
        with closing(self._connect()) as connection:
            row = connection.execute(query, params).fetchone()
        return GeneralAssemblyAttempt.model_validate_json(row[0]) if row else None

    def get_assembly_state(
        self,
        run_id: str,
        *,
        proposal_revision: int,
        review_revision: int,
    ) -> GeneralAssemblyState | None:
        current = self.get_assembly_attempt(
            run_id,
            proposal_revision=proposal_revision,
            review_revision=review_revision,
        )
        if current is None:
            return None
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT attempt_json FROM general_assembly_attempts WHERE run_id=? AND proposal_revision=? AND review_revision=? ORDER BY assembly_revision",
                (run_id, proposal_revision, review_revision),
            ).fetchall()
        by_alternative: dict[str, GeneralAssemblyAttempt] = {}
        for row in rows:
            attempt = GeneralAssemblyAttempt.model_validate_json(row[0])
            if (
                attempt.report.status == "accepted"
                and attempt.candidate is not None
            ):
                by_alternative[attempt.candidate.alternative_id] = attempt
        accepted = tuple(sorted(
            by_alternative.values(), key=lambda item: item.assembly_revision
        ))
        ambiguous = len(accepted) > 1
        status = current.report.status
        if current.report.status == "accepted":
            status = "ambiguous" if ambiguous else "accepted"
        return GeneralAssemblyState(
            run_id=run_id,
            proposal_revision=proposal_revision,
            review_revision=review_revision,
            assembly_revision=current.assembly_revision,
            status=status,
            current=current,
            accepted_alternatives=accepted,
            ambiguous=ambiguous,
        )

    def request_assembly_cancellation(
        self, job_id: str, run_id: str, requested_at: str
    ) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "INSERT OR IGNORE INTO general_assembly_cancellations VALUES(?,?,?)",
                (job_id, run_id, requested_at),
            )

    def is_assembly_cancelled(self, job_id: str, run_id: str) -> bool:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT 1 FROM general_assembly_cancellations WHERE job_id=? AND run_id=?",
                (job_id, run_id),
            ).fetchone()
        return row is not None

    def _check_size_quota(self) -> None:
        size = sum(
            path.stat().st_size
            for path in (self.path, Path(str(self.path) + "-wal"))
            if path.exists()
        )
        if size >= self.max_database_bytes:
            raise ValueError("general_furniture_storage_quota_exceeded")
