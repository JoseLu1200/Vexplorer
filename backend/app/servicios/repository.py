from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from backend.app.contratos.modelos import (
    AssemblyCandidate,
    DecompositionScenario,
    DrawingExtraction,
    Estimate,
    HumanReview,
    LibraryItem,
    ResolvedPiece,
    Result,
    ReviewRequest,
    RunSnapshot,
    SeparatedPartsExtraction,
    TableCostEstimate,
    TableDrawingExports,
    TableDrawingManifest,
    EvaluatedTableProgram,
    MountedTableAnalysis,
    TableProgramProposal,
)
from backend.app.geometria.parts import recompute_reviewed_assembly_candidate
from backend.app.geometria.mounted_table import evaluate_table_program

DIMENSION_TOLERANCE_MM = 0.1


def _now() -> str:
    return datetime.now(UTC).isoformat()


class DemoRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, mode TEXT NOT NULL, state TEXT NOT NULL,
                    reason_code TEXT, candidate_revision TEXT NOT NULL,
                    current_result_revision INTEGER, extraction_json TEXT NOT NULL,
                    scenarios_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS results (
                    run_id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY (run_id, revision)
                );
                CREATE TABLE IF NOT EXISTS estimates (
                    run_id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY (run_id, revision)
                );
                CREATE TABLE IF NOT EXISTS events (
                    run_id TEXT NOT NULL, sequence INTEGER NOT NULL, event_type TEXT NOT NULL,
                    payload TEXT NOT NULL, PRIMARY KEY (run_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS review_idempotency (
                    run_id TEXT NOT NULL, idempotency_key TEXT NOT NULL,
                    request_hash TEXT NOT NULL, result_revision INTEGER NOT NULL,
                    PRIMARY KEY (run_id, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, actor TEXT, request_json TEXT NOT NULL,
                    request_hash TEXT NOT NULL, state TEXT NOT NULL, run_id TEXT,
                    error_json TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS job_idempotency (
                    actor TEXT NOT NULL, idempotency_key TEXT NOT NULL,
                    request_hash TEXT NOT NULL, job_id TEXT NOT NULL,
                    PRIMARY KEY (actor, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS library_items (
                    run_id TEXT PRIMARY KEY, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS embedding_cache (
                    cache_key TEXT PRIMARY KEY, model TEXT NOT NULL, dimensions INTEGER NOT NULL,
                    descriptor_version TEXT NOT NULL, vector_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS table_cost_estimates (
                    run_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    estimate_id TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY (run_id, revision, estimate_id)
                );
                CREATE TABLE IF NOT EXISTS table_drawing_manifests (
                    run_id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY (run_id, revision)
                );
                CREATE TABLE IF NOT EXISTS table_drawing_artifacts (
                    run_id TEXT NOT NULL, revision INTEGER NOT NULL, sheet_id TEXT NOT NULL,
                    format TEXT NOT NULL, program_hash TEXT NOT NULL, media_type TEXT NOT NULL,
                    filename TEXT NOT NULL, content BLOB NOT NULL,
                    PRIMARY KEY (run_id, revision, sheet_id, format)
                );
                """
            )
            columns = {row[1] for row in db.execute("PRAGMA table_info(runs)").fetchall()}
            if "agent_selected_scenario_id" not in columns:
                db.execute("ALTER TABLE runs ADD COLUMN agent_selected_scenario_id TEXT")
            if "document_id" not in columns:
                db.execute("ALTER TABLE runs ADD COLUMN document_id TEXT")
            if "input_kind" not in columns:
                db.execute("ALTER TABLE runs ADD COLUMN input_kind TEXT NOT NULL DEFAULT 'mounted_views_legacy'")
            if "agent_selected_assembly_candidate_id" not in columns:
                db.execute("ALTER TABLE runs ADD COLUMN agent_selected_assembly_candidate_id TEXT")
            if "agent_selected_table_program_id" not in columns:
                db.execute("ALTER TABLE runs ADD COLUMN agent_selected_table_program_id TEXT")
            cost_columns = db.execute("PRAGMA table_info(table_cost_estimates)").fetchall()
            if cost_columns and "estimate_id" not in {row[1] for row in cost_columns}:
                db.execute("ALTER TABLE table_cost_estimates RENAME TO table_cost_estimates_legacy")
                db.execute(
                    "CREATE TABLE table_cost_estimates (run_id TEXT NOT NULL, revision INTEGER NOT NULL, estimate_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY (run_id, revision, estimate_id))"
                )
                for row in db.execute(
                    "SELECT run_id,revision,payload FROM table_cost_estimates_legacy"
                ).fetchall():
                    payload = json.loads(row["payload"])
                    estimate_id = payload.get("estimate_id") or hashlib.sha256(
                        row["payload"].encode("utf-8")
                    ).hexdigest()
                    db.execute(
                        "INSERT INTO table_cost_estimates VALUES (?, ?, ?, ?)",
                        (row["run_id"], row["revision"], estimate_id, row["payload"]),
                    )
                db.execute("DROP TABLE table_cost_estimates_legacy")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def create_run(self, run_id: str, mode: str, extraction: DrawingExtraction, scenarios: tuple[DecompositionScenario, ...], trace_events: tuple[dict, ...] = (), agent_selected_scenario_id: str | None = None, document_id: str | None = None, part_analysis: SeparatedPartsExtraction | None = None, assembly_candidates: tuple[AssemblyCandidate, ...] = (), agent_selected_assembly_candidate_id: str | None = None, table_analysis: MountedTableAnalysis | None = None, table_programs: tuple[TableProgramProposal, ...] = (), agent_selected_table_program_id: str | None = None, evaluated_table_program: EvaluatedTableProgram | None = None) -> RunSnapshot:
        created_at = _now()
        input_semantics = extraction.input_kind
        candidate_revision = part_analysis.candidate_revision if part_analysis is not None else table_analysis.ledger_revision if table_analysis is not None else extraction.drawing_id
        initial = Result(run_id=run_id, result_revision=1, state="needs_review", scenarios=scenarios, pieces=(), created_at=created_at, agent_selected_scenario_id=agent_selected_scenario_id, input_semantics=input_semantics, part_analysis=part_analysis, assembly_candidates=assembly_candidates, table_analysis=table_analysis, table_programs=table_programs, evaluated_table_program=evaluated_table_program)
        with self._connect() as db:
            db.execute(
                "INSERT INTO runs (id,mode,state,reason_code,candidate_revision,current_result_revision,extraction_json,scenarios_json,created_at,agent_selected_scenario_id,document_id,input_kind,agent_selected_assembly_candidate_id,agent_selected_table_program_id) VALUES (?, ?, 'needs_review', NULL, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, mode, candidate_revision, extraction.model_dump_json(), json.dumps([item.model_dump(mode="json") for item in scenarios]), created_at, agent_selected_scenario_id, document_id, extraction.input_kind, agent_selected_assembly_candidate_id, agent_selected_table_program_id),
            )
            db.execute("INSERT INTO results VALUES (?, 1, ?)", (run_id, initial.model_dump_json()))
            sequence = 1
            db.execute("INSERT INTO events VALUES (?, ?, 'run_state_changed', ?)", (run_id, sequence, json.dumps({"timestamp": created_at, "state": "needs_review", "mode": mode})))
            for trace in trace_events:
                sequence += 1
                db.execute("INSERT INTO events VALUES (?, ?, 'tool_completed', ?)", (run_id, sequence, json.dumps({"timestamp": created_at, **trace})))
            sequence += 1
            db.execute("INSERT INTO events VALUES (?, ?, 'result_committed', ?)", (run_id, sequence, json.dumps({"timestamp": created_at, "result_revision": 1, "state": "needs_review"})))
            sequence += 1
            db.execute("INSERT INTO events VALUES (?, ?, 'run_finished', ?)", (run_id, sequence, json.dumps({"timestamp": created_at, "state": "needs_review", "result_revision": 1})))
        return self.get_run(run_id)

    def reserve_job(
        self,
        job_id: str,
        request_json: str,
        *,
        actor: str | None,
        idempotency_key: str | None = None,
    ) -> tuple[dict, bool]:
        request_hash = hashlib.sha256(request_json.encode("utf-8")).hexdigest()
        actor_key = actor or "local-demo"
        timestamp = _now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if idempotency_key is not None:
                replay = db.execute(
                    "SELECT request_hash,job_id FROM job_idempotency WHERE actor=? AND idempotency_key=?",
                    (actor_key, idempotency_key),
                ).fetchone()
                if replay is not None:
                    if replay["request_hash"] != request_hash:
                        raise ValueError("idempotency_key_conflict")
                    return self._get_job_in_transaction(db, replay["job_id"]), False
            db.execute(
                "INSERT INTO jobs VALUES (?, ?, ?, ?, 'queued', NULL, NULL, ?, ?)",
                (job_id, actor, request_json, request_hash, timestamp, timestamp),
            )
            if idempotency_key is not None:
                db.execute(
                    "INSERT INTO job_idempotency VALUES (?, ?, ?, ?)",
                    (actor_key, idempotency_key, request_hash, job_id),
                )
            return self._get_job_in_transaction(db, job_id), True

    def get_idempotent_job(
        self,
        request_json: str,
        *,
        actor: str | None,
        idempotency_key: str,
    ) -> dict | None:
        request_hash = hashlib.sha256(request_json.encode("utf-8")).hexdigest()
        actor_key = actor or "local-demo"
        with self._connect() as db:
            replay = db.execute(
                "SELECT request_hash,job_id FROM job_idempotency WHERE actor=? AND idempotency_key=?",
                (actor_key, idempotency_key),
            ).fetchone()
            if replay is None:
                return None
            if replay["request_hash"] != request_hash:
                raise ValueError("idempotency_key_conflict")
            return self._get_job_in_transaction(db, replay["job_id"])

    def create_job(self, job_id: str, request_json: str, *, actor: str | None) -> dict:
        return self.reserve_job(job_id, request_json, actor=actor)[0]

    @staticmethod
    def _get_job_in_transaction(db: sqlite3.Connection, job_id: str) -> dict:
        row = db.execute(
            "SELECT id,state,run_id,error_json FROM jobs WHERE id=?", (job_id,)
        ).fetchone()
        if row is None:
            raise KeyError(job_id)
        return {
            "id": row["id"], "state": row["state"], "run_id": row["run_id"],
            "error": json.loads(row["error_json"]) if row["error_json"] else None,
        }

    def get_job(self, job_id: str) -> dict:
        with self._connect() as db:
            return self._get_job_in_transaction(db, job_id)

    def get_job_request(self, job_id: str) -> str:
        with self._connect() as db:
            row = db.execute("SELECT request_json FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return row["request_json"]

    def start_job(self, job_id: str) -> None:
        with self._connect() as db:
            changed = db.execute(
                "UPDATE jobs SET state='running',updated_at=? WHERE id=? AND state='queued'",
                (_now(), job_id),
            )
            if changed.rowcount != 1:
                raise ValueError("job_not_queued")

    def finish_job(
        self, job_id: str, *, run_id: str | None = None, error: dict | None = None
    ) -> None:
        state = "succeeded" if run_id is not None else "failed"
        with self._connect() as db:
            changed = db.execute(
                "UPDATE jobs SET state=?,run_id=?,error_json=?,updated_at=? WHERE id=? AND state='running'",
                (state, run_id, json.dumps(error) if error else None, _now(), job_id),
            )
            if changed.rowcount != 1:
                raise ValueError("job_not_running")

    def interrupt_unfinished_jobs(self) -> int:
        error = json.dumps({
            "code": "server_restarted",
            "message": "El trabajo fue interrumpido por un reinicio y no se reejecutará.",
            "retryable": False,
        })
        with self._connect() as db:
            changed = db.execute(
                "UPDATE jobs SET state='interrupted',error_json=?,updated_at=? WHERE state IN ('queued','running')",
                (error, _now()),
            )
            return changed.rowcount

    def get_run(self, run_id: str) -> RunSnapshot:
        with self._connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return RunSnapshot(id=row["id"], mode=row["mode"], state=row["state"], reason_code=row["reason_code"], candidate_revision=row["candidate_revision"], result_revision=row["current_result_revision"], created_at=row["created_at"], agent_selected_scenario_id=row["agent_selected_scenario_id"], agent_selected_assembly_candidate_id=row["agent_selected_assembly_candidate_id"], agent_selected_table_program_id=row["agent_selected_table_program_id"], document_id=row["document_id"], input_kind=row["input_kind"])

    def get_extraction(self, run_id: str) -> DrawingExtraction:
        with self._connect() as db:
            row = db.execute("SELECT extraction_json FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return DrawingExtraction.model_validate_json(row[0])

    def get_result(self, run_id: str, revision: int | None = None) -> Result:
        if revision is None:
            revision = self.get_run(run_id).result_revision
        with self._connect() as db:
            row = db.execute("SELECT payload FROM results WHERE run_id=? AND revision=?", (run_id, revision)).fetchone()
        if row is None:
            raise KeyError((run_id, revision))
        return Result.model_validate_json(row[0])

    def get_results(self, run_id: str) -> tuple[Result, ...]:
        self.get_run(run_id)
        with self._connect() as db:
            rows = db.execute("SELECT payload FROM results WHERE run_id=? ORDER BY revision", (run_id,)).fetchall()
        return tuple(Result.model_validate_json(row[0]) for row in rows)

    def review(
        self,
        run_id: str,
        request: ReviewRequest,
        *,
        idempotency_key: str | None = None,
        actor: str | None = None,
    ) -> Result:
        if actor is not None:
            request = request.model_copy(update={"reviewer_name": actor})
        request_hash = hashlib.sha256(request.model_dump_json().encode("utf-8")).hexdigest()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if idempotency_key is not None:
                replay = db.execute(
                    "SELECT request_hash,result_revision FROM review_idempotency WHERE run_id=? AND idempotency_key=?",
                    (run_id, idempotency_key),
                ).fetchone()
                if replay is not None:
                    if replay["request_hash"] != request_hash:
                        raise ValueError("idempotency_key_conflict")
                    row = db.execute(
                        "SELECT payload FROM results WHERE run_id=? AND revision=?",
                        (run_id, replay["result_revision"]),
                    ).fetchone()
                    if row is None:
                        raise RuntimeError("idempotency_result_missing")
                    return Result.model_validate_json(row["payload"])
            run_row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if run_row is None:
                raise KeyError(run_id)
            if request.base_result_revision != run_row["current_result_revision"]:
                raise ValueError("stale_result_revision")
            previous_row = db.execute(
                "SELECT payload FROM results WHERE run_id=? AND revision=?",
                (run_id, request.base_result_revision),
            ).fetchone()
            if previous_row is None:
                raise KeyError((run_id, request.base_result_revision))
            previous = Result.model_validate_json(previous_row["payload"])
            if previous.input_semantics == "mounted_orthographic_views":
                result = self._review_table(run_id, previous, request)
            elif previous.input_semantics == "separated_part_views":
                result = self._review_parts(run_id, previous, request)
            else:
                result = self._review_legacy(run_id, previous, request)
            reserved = db.execute(
                "UPDATE runs SET current_result_revision=? WHERE id=? AND current_result_revision=?",
                (result.result_revision, run_id, request.base_result_revision),
            )
            if reserved.rowcount != 1:
                raise ValueError("stale_result_revision")
            db.execute(
                "INSERT INTO results VALUES (?, ?, ?)",
                (run_id, result.result_revision, result.model_dump_json()),
            )
            self._append_event_in_transaction(
                db, run_id, "human_review_committed",
                {
                    "result_revision": result.result_revision,
                    "reviewer_name": request.reviewer_name,
                    "selected_scenario_id": request.scenario_id,
                    "selected_assembly_candidate_id": request.assembly_candidate_id,
                    "selected_table_program_id": request.table_program_id,
                },
            )
            if idempotency_key is not None:
                db.execute(
                    "INSERT INTO review_idempotency VALUES (?, ?, ?, ?)",
                    (run_id, idempotency_key, request_hash, result.result_revision),
                )
            return result

    def _review_legacy(self, run_id: str, previous: Result, request: ReviewRequest) -> Result:
        proposals = {proposal.id: proposal for scenario in previous.scenarios for proposal in scenario.components}
        proposal_scenarios = {proposal.id: scenario.id for scenario in previous.scenarios for proposal in scenario.components}
        pieces: list[ResolvedPiece] = []
        rejected: list[str] = []
        selected_scenario_id = request.scenario_id
        if request.decisions:
            decision_scenarios = {proposal_scenarios.get(item.proposal_id) for item in request.decisions}
            if None in decision_scenarios:
                raise ValueError("unknown_proposal")
            if len(decision_scenarios) != 1:
                raise ValueError("incompatible_scenario_selection")
            selected_scenario_id = next(iter(decision_scenarios))
            rejected.extend(proposal.id for scenario in previous.scenarios if scenario.id != selected_scenario_id for proposal in scenario.components)
        if request.scenario_id is not None:
            selected = next((item for item in previous.scenarios if item.id == request.scenario_id), None)
            if selected is None:
                raise ValueError("unknown_scenario")
            thickness = request.confirmed_thickness_mm
            assert thickness is not None and request.notes is not None
            for proposal in selected.components:
                length = proposal.length_mm
                if proposal.length_derivation in ("overall_width_minus_two_thickness", "overall_height_minus_two_thickness"):
                    assert proposal.length_basis_mm is not None
                    length = proposal.length_basis_mm - 2 * thickness
                if length is not None and length <= 0:
                    raise ValueError("invalid_derived_dimension")
                length_state = "observed" if proposal.length_derivation == "direct_observation" else "calculated"
                pieces.append(ResolvedPiece(id=f"piece-{proposal.id}", proposal_id=proposal.id, label=proposal.label, role=proposal.role, quantity=proposal.quantity, length_mm=length, width_mm=proposal.width_mm, thickness_mm=thickness, material=request.material, finish=request.finish, source_observation_ids=proposal.source_observation_ids, source_contour_ids=proposal.source_contour_ids, evidence_ids=proposal.evidence_ids, human_confirmation=request.notes, field_states={"quantity": "confirmed", "length_mm": length_state, "width_mm": "observed", "thickness_mm": "confirmed", "material": "confirmed" if request.material else "unknown", "finish": "confirmed" if request.finish else "unknown"}))
            rejected.extend(proposal.id for scenario in previous.scenarios if scenario.id != selected.id for proposal in scenario.components)
        for decision in request.decisions:
            proposal = proposals.get(decision.proposal_id)
            if proposal is None:
                raise ValueError("unknown_proposal")
            if decision.action == "reject":
                rejected.append(decision.proposal_id)
                continue
            pieces.append(
                ResolvedPiece(
                    id=f"piece-{decision.proposal_id}", proposal_id=proposal.id, label=proposal.label,
                    role=decision.role, quantity=decision.quantity, length_mm=decision.length_mm,
                    width_mm=decision.width_mm, thickness_mm=decision.thickness_mm,
                    material=decision.material, finish=decision.finish,
                    source_observation_ids=proposal.source_observation_ids,
                    source_contour_ids=proposal.source_contour_ids, evidence_ids=proposal.evidence_ids,
                    human_confirmation=decision.notes,
                    field_states={"quantity": "confirmed" if decision.quantity else "unknown", "length_mm": "confirmed" if decision.length_mm else "unknown", "width_mm": "confirmed" if decision.width_mm else "unknown", "thickness_mm": "confirmed" if decision.thickness_mm else "unknown", "material": "confirmed" if decision.material else "unknown", "finish": "confirmed" if decision.finish else "unknown"},
                )
            )
        selected_proposals = {item.proposal_id for item in pieces}
        covered = selected_proposals | set(rejected)
        rejected_in_selected = {item for item in rejected if proposal_scenarios.get(item) == selected_scenario_id}
        complete = bool(pieces) and covered == set(proposals) and not rejected_in_selected and all(
            item.quantity is not None and item.length_mm is not None and item.width_mm is not None and item.thickness_mm is not None
            for item in pieces
        )
        revision = request.base_result_revision + 1
        timestamp = _now()
        reason = request.notes or "; ".join(item.notes for item in request.decisions)
        result = Result(run_id=run_id, result_revision=revision, state="completed" if complete else "needs_review", scenarios=previous.scenarios, pieces=tuple(pieces), rejected_proposal_ids=tuple(rejected), created_at=timestamp, review=HumanReview(reviewer_name=request.reviewer_name, reason=reason, timestamp=timestamp, selected_scenario_id=selected_scenario_id), agent_selected_scenario_id=previous.agent_selected_scenario_id)
        return result

    def _review_table(self, run_id: str, previous: Result, request: ReviewRequest) -> Result:
        if request.table_program_id is None or previous.table_analysis is None:
            raise ValueError("table_program_required")
        program = next((item for item in previous.table_programs if item.id == request.table_program_id), None)
        if program is None:
            raise ValueError("unknown_table_program")
        if previous.selected_table_program_id == program.id:
            decisions = {(item.target_kind, item.target_id): item for item in previous.table_review_decisions}
            confirmed = {item.target_id: item for item in previous.table_confirmed_values}
            corrections = {item.measurement_id: item for item in previous.table_observed_value_corrections}
            source_decisions = {item.warning_id: item for item in previous.table_source_review_decisions}
        else:
            decisions, confirmed, corrections, source_decisions = {}, {}, {}, {}
        decisions.update({(item.target_kind, item.target_id): item for item in request.table_decisions})
        existing_confirmation_ids = {
            item.confirmation_id: target
            for target, item in confirmed.items()
            if item.confirmation_id is not None
        }
        for item in request.table_confirmed_values:
            current = confirmed.get(item.target_id)
            if current is None:
                if item.supersedes_confirmation_id is not None:
                    raise ValueError("unknown_superseded_confirmation")
            elif current.confirmation_id is not None:
                if item.supersedes_confirmation_id != current.confirmation_id:
                    raise ValueError("stale_confirmation_supersedes")
            elif item.supersedes_confirmation_id is not None:
                raise ValueError("unknown_superseded_confirmation")
            owner = existing_confirmation_ids.get(item.confirmation_id)
            if item.confirmation_id is not None and owner not in (None, item.target_id):
                raise ValueError("duplicate_confirmation_id")
            confirmed[item.target_id] = item
        existing_correction_ids = {
            item.correction_id: target for target, item in corrections.items()
        }
        for item in request.table_observed_value_corrections:
            current = corrections.get(item.measurement_id)
            if current is None:
                if item.supersedes_correction_id is not None:
                    raise ValueError("unknown_superseded_correction")
            elif item.supersedes_correction_id != current.correction_id:
                raise ValueError("stale_correction_supersedes")
            owner = existing_correction_ids.get(item.correction_id)
            if owner not in (None, item.measurement_id):
                raise ValueError("duplicate_correction_id")
            corrections[item.measurement_id] = item
        source_decisions.update({item.warning_id: item for item in request.table_source_review_decisions})
        effective_decisions = tuple(decisions[key] for key in sorted(decisions))
        effective_confirmed = tuple(confirmed[key] for key in sorted(confirmed))
        effective_corrections = tuple(corrections[key] for key in sorted(corrections))
        effective_source_decisions = tuple(source_decisions[key] for key in sorted(source_decisions))
        evaluated = evaluate_table_program(
            previous.table_analysis,
            program,
            effective_decisions,
            effective_confirmed,
            effective_corrections,
            effective_source_decisions,
        )
        revision = request.base_result_revision + 1
        timestamp = _now()
        result = Result(
            run_id=run_id, result_revision=revision,
            state="completed" if evaluated.state == "completed" else "needs_review",
            scenarios=previous.scenarios, pieces=(), created_at=timestamp,
            review=HumanReview(reviewer_name=request.reviewer_name, reason=request.notes or "Revisión de programa de mesa", timestamp=timestamp, selected_scenario_id=None, selected_table_program_id=program.id),
            input_semantics=previous.input_semantics,
            table_analysis=previous.table_analysis, table_programs=previous.table_programs,
            selected_table_program_id=program.id, evaluated_table_program=evaluated,
            table_review_decisions=effective_decisions, table_confirmed_values=effective_confirmed,
            table_observed_value_corrections=effective_corrections,
            table_source_review_decisions=effective_source_decisions,
        )
        return result

    def _review_parts(self, run_id: str, previous: Result, request: ReviewRequest) -> Result:
        if request.assembly_candidate_id is None or previous.part_analysis is None:
            raise ValueError("assembly_candidate_required")
        candidate = next((item for item in previous.assembly_candidates if item.id == request.assembly_candidate_id), None)
        if candidate is None:
            raise ValueError("unknown_assembly_candidate")
        observations = {item.id: item for item in previous.part_analysis.observations}
        covered = {item.part_observation_id for item in candidate.uses} | set(candidate.unassigned_part_observation_ids)
        if covered != set(observations):
            raise ValueError("incomplete_part_coverage")
        decisions = {item.proposal_id: item for item in request.decisions}
        if not set(decisions) <= {item.id for item in candidate.uses}:
            raise ValueError("unknown_proposal")
        pieces: list[ResolvedPiece] = []
        rejected: list[str] = []
        previous_pieces = {
            item.proposal_id: item for item in previous.pieces
        } if previous.selected_assembly_candidate_id == candidate.id else {}
        for use in candidate.uses:
            observation = observations[use.part_observation_id]
            previous_piece = previous_pieces.get(use.id)
            if use.quantity_source == "observed_annotation":
                if observation.quantity.state != "observed" or use.source_quantity != observation.quantity.value or set(use.evidence_ids) != set(observation.quantity.evidence_ids):
                    raise ValueError("quantity_source_mismatch")
            elif use.quantity_source == "human_confirmed":
                raise ValueError("candidate_cannot_preconfirm_quantity")
            decision = decisions.get(use.id)
            if decision is not None and decision.action == "reject":
                rejected.append(use.id)
                continue
            if decision is not None and decision.role not in ("unknown", use.role):
                raise ValueError("role_override_requires_candidate")
            if (
                use.quantity_source == "observed_annotation"
                and decision is not None
                and decision.quantity is not None
                and decision.quantity != use.allocated_quantity
            ):
                raise ValueError("observed_quantity_override")
            dimensions = observation.dimensions
            quantity_confirmed = bool(
                decision and decision.quantity is not None and use.quantity_source == "unknown"
            )
            expected_quantity = {"side_panel": 2, "top_panel": 1, "base_panel": 1}.get(use.role)
            if quantity_confirmed and expected_quantity is not None and decision.quantity != expected_quantity:
                raise ValueError("incompatible_role_quantity")
            if quantity_confirmed:
                quantity = decision.quantity
                quantity_state = "confirmed"
            elif use.allocated_quantity is not None:
                quantity = use.allocated_quantity
                quantity_state = "observed"
            elif previous_piece is not None and previous_piece.field_states.get("quantity") == "confirmed":
                quantity = previous_piece.quantity
                quantity_state = "confirmed"
            else:
                quantity = None
                quantity_state = "unknown"

            def reviewed_dimension(field: str, observed):
                supplied = getattr(decision, field) if decision is not None else None
                if supplied is None:
                    if (
                        previous_piece is not None
                        and previous_piece.field_states.get(field) == "confirmed"
                        and getattr(previous_piece, field) is not None
                    ):
                        return getattr(previous_piece, field), "confirmed"
                    return observed.value_mm, observed.state if observed.state != "conflict" else "unknown"
                if observed.state == "observed":
                    if observed.value_mm is None or abs(supplied - observed.value_mm) > DIMENSION_TOLERANCE_MM:
                        raise ValueError("observed_dimension_override")
                    return observed.value_mm, "observed"
                return supplied, "confirmed"

            length, length_state = reviewed_dimension("length_mm", dimensions.length)
            width, width_state = reviewed_dimension("width_mm", dimensions.width)
            thickness, thickness_state = reviewed_dimension("thickness_mm", dimensions.thickness)
            material = decision.material if decision and decision.material is not None else request.material if request.material is not None else previous_piece.material if previous_piece else None
            finish = decision.finish if decision and decision.finish is not None else request.finish if request.finish is not None else previous_piece.finish if previous_piece else None
            changed = bool(decision or request.material is not None or request.finish is not None)
            notes = (decision.notes if decision else request.notes) if changed else previous_piece.human_confirmation if previous_piece else request.notes or ""
            pieces.append(ResolvedPiece(id=f"piece-{use.id}", proposal_id=use.id, label=f"{observation.part_key or observation.id}:{use.role}", role=use.role, quantity=quantity, length_mm=length, width_mm=width, thickness_mm=thickness, material=material, finish=finish, source_observation_ids=(), source_contour_ids=tuple(contour_id for view in observation.views for contour_id in view.contour_ids), evidence_ids=observation.evidence_ids, source_part_observation_ids=(observation.id,), human_confirmation=notes or "", field_states={"quantity": quantity_state, "length_mm": length_state, "width_mm": width_state, "thickness_mm": thickness_state, "material": "confirmed" if material else "unknown", "finish": "confirmed" if finish else "unknown"}))
        revision = request.base_result_revision + 1
        effective_candidate = recompute_reviewed_assembly_candidate(
            candidate,
            previous.part_analysis,
            tuple(pieces),
            result_revision=revision,
        )
        effective_candidates = tuple(
            effective_candidate if item.id == effective_candidate.id else item
            for item in previous.assembly_candidates
        )
        dimensions_complete = all(item.quantity is not None and item.length_mm is not None and item.width_mm is not None and item.thickness_mm is not None for item in pieces)
        assembly_complete = effective_candidate.family != "unknown" and effective_candidate.layout != "unknown" and not effective_candidate.unassigned_part_observation_ids and not rejected and len(pieces) == len(effective_candidate.uses) and all(item.status == "pass" for item in effective_candidate.constraints) and {item.axis for item in effective_candidate.derived_dimensions} == {"width", "height", "depth"} and all(item.state == "derived" for item in effective_candidate.derived_dimensions)
        timestamp = _now()
        result = Result(run_id=run_id, result_revision=revision, state="completed" if dimensions_complete and assembly_complete else "needs_review", scenarios=(), pieces=tuple(pieces), rejected_proposal_ids=tuple(rejected), created_at=timestamp, review=HumanReview(reviewer_name=request.reviewer_name, reason=request.notes or "; ".join(item.notes for item in request.decisions), timestamp=timestamp, selected_scenario_id=None, selected_assembly_candidate_id=effective_candidate.id), input_semantics="separated_part_views", part_analysis=previous.part_analysis, assembly_candidates=effective_candidates, selected_assembly_candidate_id=effective_candidate.id)
        return result

    def save_estimate(self, run_id: str, estimate: Estimate) -> None:
        if self.get_result(run_id, estimate.result_revision).result_revision != estimate.result_revision:
            raise ValueError("result_revision_mismatch")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            payload = estimate.model_dump_json()
            existing = db.execute(
                "SELECT payload FROM estimates WHERE run_id=? AND revision=?",
                (run_id, estimate.result_revision),
            ).fetchone()
            if existing is not None:
                if existing["payload"] != payload:
                    raise ValueError("economic_revision_conflict")
                return
            db.execute("INSERT INTO estimates VALUES (?, ?, ?)", (run_id, estimate.result_revision, payload))
            self._append_event_in_transaction(
                db, run_id, "estimate_committed",
                {"result_revision": estimate.result_revision, "total": estimate.total, "currency": estimate.currency},
            )

    def get_estimate(self, run_id: str, revision: int) -> Estimate:
        with self._connect() as db:
            row = db.execute("SELECT payload FROM estimates WHERE run_id=? AND revision=?", (run_id, revision)).fetchone()
        if row is None:
            raise KeyError((run_id, revision))
        return Estimate.model_validate_json(row[0])

    def get_events(self, run_id: str) -> tuple[dict, ...]:
        self.get_run(run_id)
        with self._connect() as db:
            rows = db.execute("SELECT sequence,event_type,payload FROM events WHERE run_id=? ORDER BY sequence", (run_id,)).fetchall()
        return tuple({"sequence": row["sequence"], "event_type": row["event_type"], "data": json.loads(row["payload"])} for row in rows)

    def append_event(self, run_id: str, event_type: str, payload: dict) -> None:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM runs WHERE id=?", (run_id,)).fetchone() is None:
                raise KeyError(run_id)
            self._append_event_in_transaction(db, run_id, event_type, payload)

    @staticmethod
    def _append_event_in_transaction(
        db: sqlite3.Connection, run_id: str, event_type: str, payload: dict
    ) -> None:
        stamped = {"timestamp": _now(), **payload}
        sequence = db.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM events WHERE run_id=?",
            (run_id,),
        ).fetchone()[0]
        db.execute(
            "INSERT INTO events VALUES (?, ?, ?, ?)",
            (run_id, sequence, event_type, json.dumps(stamped)),
        )

    def save_library_item(self, item: LibraryItem) -> None:
        self.get_result(item.run_id, item.result_revision)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR REPLACE INTO library_items (run_id,payload) VALUES (?, ?)", (item.run_id, item.model_dump_json()))
            self._append_event_in_transaction(
                db, item.run_id, "library_item_saved", {"result_revision": item.result_revision}
            )

    def get_library_items(self) -> tuple[LibraryItem, ...]:
        with self._connect() as db:
            rows = db.execute("SELECT payload FROM library_items ORDER BY run_id").fetchall()
        return tuple(LibraryItem.model_validate_json(row[0]) for row in rows)

    def get_library_item(self, run_id: str) -> LibraryItem:
        with self._connect() as db:
            row = db.execute("SELECT payload FROM library_items WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return LibraryItem.model_validate_json(row[0])

    def save_embedding(self, cache_key: str, model: str, dimensions: int, descriptor_version: str, vector: tuple[float, ...]) -> None:
        from backend.app.semantic.embeddings import validate_embedding

        validated = validate_embedding(list(vector), dimensions)
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO embedding_cache VALUES (?, ?, ?, ?, ?, ?)", (cache_key, model, dimensions, descriptor_version, json.dumps(validated), _now()))

    def get_embedding(self, cache_key: str, model: str, dimensions: int, descriptor_version: str) -> tuple[float, ...]:
        from backend.app.semantic.embeddings import validate_embedding

        with self._connect() as db:
            row = db.execute("SELECT model,dimensions,descriptor_version,vector_json FROM embedding_cache WHERE cache_key=?", (cache_key,)).fetchone()
        if row is None:
            raise KeyError(cache_key)
        if row["model"] != model or row["dimensions"] != dimensions or row["descriptor_version"] != descriptor_version:
            raise ValueError("embedding_space_incompatible")
        return validate_embedding(json.loads(row["vector_json"]), dimensions)

    def save_table_cost_estimate(self, run_id: str, estimate: TableCostEstimate) -> None:
        result = self.get_result(run_id, estimate.result_revision)
        evaluated = result.evaluated_table_program
        if evaluated is None or evaluated.program_hash != estimate.program_hash:
            raise ValueError("table_program_revision_mismatch")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            payload = estimate.model_dump_json()
            estimate_id = estimate.estimate_id or hashlib.sha256(payload.encode("utf-8")).hexdigest()
            existing = db.execute(
                "SELECT payload FROM table_cost_estimates WHERE run_id=? AND revision=? AND estimate_id=?",
                (run_id, estimate.result_revision, estimate_id),
            ).fetchone()
            if existing is not None:
                if existing["payload"] != payload:
                    raise ValueError("economic_revision_conflict")
                return
            db.execute(
                "INSERT INTO table_cost_estimates VALUES (?, ?, ?, ?)",
                (run_id, estimate.result_revision, estimate_id, payload),
            )
            self._append_event_in_transaction(
                db, run_id, "table_cost_committed",
                {"result_revision": estimate.result_revision, "estimate_id": estimate_id, "program_hash": estimate.program_hash, "total_state": estimate.total_state},
            )

    def get_table_cost_estimate(
        self, run_id: str, revision: int, estimate_id: str | None = None
    ) -> TableCostEstimate:
        self.get_result(run_id, revision)
        with self._connect() as db:
            if estimate_id is None:
                row = db.execute(
                    "SELECT payload FROM table_cost_estimates WHERE run_id=? AND revision=? ORDER BY rowid DESC LIMIT 1",
                    (run_id, revision),
                ).fetchone()
            else:
                row = db.execute(
                    "SELECT payload FROM table_cost_estimates WHERE run_id=? AND revision=? AND estimate_id=?",
                    (run_id, revision, estimate_id),
                ).fetchone()
        if row is None:
            raise KeyError((run_id, revision))
        return TableCostEstimate.model_validate_json(row[0])

    def save_table_drawings(self, run_id: str, manifest: TableDrawingManifest, exports: TableDrawingExports) -> None:
        if manifest.result_revision != exports.result_revision or manifest.program_hash != exports.program_hash:
            raise ValueError("table_drawing_bundle_mismatch")
        result = self.get_result(run_id, manifest.result_revision)
        evaluated = result.evaluated_table_program
        if evaluated is None or evaluated.program_hash != manifest.program_hash or manifest.run_id != run_id:
            raise ValueError("table_program_revision_mismatch")
        links = {(sheet.sheet_id, link.format) for sheet in manifest.sheets for link in sheet.formats}
        artifacts = {(item.sheet_id, item.format) for item in exports.artifacts}
        if links != artifacts:
            raise ValueError("table_drawing_manifest_mismatch")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR REPLACE INTO table_drawing_manifests VALUES (?, ?, ?)", (run_id, manifest.result_revision, manifest.model_dump_json()))
            db.execute("DELETE FROM table_drawing_artifacts WHERE run_id=? AND revision=?", (run_id, manifest.result_revision))
            db.executemany(
                "INSERT INTO table_drawing_artifacts VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ((run_id, manifest.result_revision, item.sheet_id, item.format, manifest.program_hash, item.media_type, item.filename, item.content) for item in exports.artifacts),
            )
            self._append_event_in_transaction(
                db, run_id, "table_drawings_committed",
                {"result_revision": manifest.result_revision, "program_hash": manifest.program_hash, "sheet_count": len(manifest.sheets)},
            )

    def get_table_drawing_manifest(self, run_id: str, revision: int) -> TableDrawingManifest:
        self.get_result(run_id, revision)
        with self._connect() as db:
            row = db.execute("SELECT payload FROM table_drawing_manifests WHERE run_id=? AND revision=?", (run_id, revision)).fetchone()
        if row is None:
            raise KeyError((run_id, revision))
        return TableDrawingManifest.model_validate_json(row[0])

    def get_table_drawing_artifact(self, run_id: str, revision: int, sheet_id: str, format: str, program_hash: str) -> tuple[bytes, str, str]:
        self.get_result(run_id, revision)
        with self._connect() as db:
            row = db.execute(
                "SELECT content,media_type,filename,program_hash FROM table_drawing_artifacts WHERE run_id=? AND revision=? AND sheet_id=? AND format=?",
                (run_id, revision, sheet_id, format),
            ).fetchone()
        if row is None:
            raise KeyError((run_id, revision, sheet_id, format))
        if row["program_hash"] != program_hash:
            raise ValueError("table_program_revision_mismatch")
        return bytes(row["content"]), row["media_type"], row["filename"]
