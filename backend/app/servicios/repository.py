from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from backend.app.contratos.modelos import (
    DecompositionScenario,
    DrawingExtraction,
    Estimate,
    HumanReview,
    LibraryItem,
    ResolvedPiece,
    Result,
    ReviewRequest,
    RunSnapshot,
)


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
                CREATE TABLE IF NOT EXISTS library_items (
                    run_id TEXT PRIMARY KEY, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS embedding_cache (
                    cache_key TEXT PRIMARY KEY, model TEXT NOT NULL, dimensions INTEGER NOT NULL,
                    descriptor_version TEXT NOT NULL, vector_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                """
            )
            columns = {row[1] for row in db.execute("PRAGMA table_info(runs)").fetchall()}
            if "agent_selected_scenario_id" not in columns:
                db.execute("ALTER TABLE runs ADD COLUMN agent_selected_scenario_id TEXT")
            if "document_id" not in columns:
                db.execute("ALTER TABLE runs ADD COLUMN document_id TEXT")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def create_run(self, run_id: str, mode: str, extraction: DrawingExtraction, scenarios: tuple[DecompositionScenario, ...], trace_events: tuple[dict, ...] = (), agent_selected_scenario_id: str | None = None, document_id: str | None = None) -> RunSnapshot:
        created_at = _now()
        initial = Result(run_id=run_id, result_revision=1, state="needs_review", scenarios=scenarios, pieces=(), created_at=created_at, agent_selected_scenario_id=agent_selected_scenario_id)
        with self._connect() as db:
            db.execute(
                "INSERT INTO runs (id,mode,state,reason_code,candidate_revision,current_result_revision,extraction_json,scenarios_json,created_at,agent_selected_scenario_id,document_id) VALUES (?, ?, 'needs_review', NULL, ?, 1, ?, ?, ?, ?, ?)",
                (run_id, mode, extraction.drawing_id, extraction.model_dump_json(), json.dumps([item.model_dump(mode="json") for item in scenarios]), created_at, agent_selected_scenario_id, document_id),
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

    def get_run(self, run_id: str) -> RunSnapshot:
        with self._connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return RunSnapshot(id=row["id"], mode=row["mode"], state=row["state"], reason_code=row["reason_code"], candidate_revision=row["candidate_revision"], result_revision=row["current_result_revision"], created_at=row["created_at"], agent_selected_scenario_id=row["agent_selected_scenario_id"], document_id=row["document_id"])

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

    def review(self, run_id: str, request: ReviewRequest) -> Result:
        run = self.get_run(run_id)
        if request.base_result_revision != run.result_revision:
            raise ValueError("stale_result_revision")
        previous = self.get_result(run_id)
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
        with self._connect() as db:
            reserved = db.execute("UPDATE runs SET current_result_revision=? WHERE id=? AND current_result_revision=?", (revision, run_id, request.base_result_revision))
            if reserved.rowcount != 1:
                raise ValueError("stale_result_revision")
            db.execute("INSERT INTO results VALUES (?, ?, ?)", (run_id, revision, result.model_dump_json()))
        return result

    def save_estimate(self, run_id: str, estimate: Estimate) -> None:
        if self.get_result(run_id, estimate.result_revision).result_revision != estimate.result_revision:
            raise ValueError("result_revision_mismatch")
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO estimates VALUES (?, ?, ?)", (run_id, estimate.result_revision, estimate.model_dump_json()))

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
        self.get_run(run_id)
        stamped = {"timestamp": _now(), **payload}
        with self._connect() as db:
            sequence = db.execute("SELECT COALESCE(MAX(sequence), 0) + 1 FROM events WHERE run_id=?", (run_id,)).fetchone()[0]
            db.execute("INSERT INTO events VALUES (?, ?, ?, ?)", (run_id, sequence, event_type, json.dumps(stamped)))

    def save_library_item(self, item: LibraryItem) -> None:
        self.get_result(item.run_id, item.result_revision)
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO library_items (run_id,payload) VALUES (?, ?)", (item.run_id, item.model_dump_json()))

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
