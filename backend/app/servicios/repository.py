from __future__ import annotations

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
)
from backend.app.geometria.parts import recompute_reviewed_assembly_candidate

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
                CREATE TABLE IF NOT EXISTS library_items (
                    run_id TEXT PRIMARY KEY, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS embedding_cache (
                    cache_key TEXT PRIMARY KEY, model TEXT NOT NULL, dimensions INTEGER NOT NULL,
                    descriptor_version TEXT NOT NULL, vector_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS table_cost_estimates (
                    run_id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY (run_id, revision)
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

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def create_run(self, run_id: str, mode: str, extraction: DrawingExtraction, scenarios: tuple[DecompositionScenario, ...], trace_events: tuple[dict, ...] = (), agent_selected_scenario_id: str | None = None, document_id: str | None = None, part_analysis: SeparatedPartsExtraction | None = None, assembly_candidates: tuple[AssemblyCandidate, ...] = (), agent_selected_assembly_candidate_id: str | None = None) -> RunSnapshot:
        created_at = _now()
        input_semantics = extraction.input_kind
        candidate_revision = part_analysis.candidate_revision if part_analysis is not None else extraction.drawing_id
        initial = Result(run_id=run_id, result_revision=1, state="needs_review", scenarios=scenarios, pieces=(), created_at=created_at, agent_selected_scenario_id=agent_selected_scenario_id, input_semantics=input_semantics, part_analysis=part_analysis, assembly_candidates=assembly_candidates)
        with self._connect() as db:
            db.execute(
                "INSERT INTO runs (id,mode,state,reason_code,candidate_revision,current_result_revision,extraction_json,scenarios_json,created_at,agent_selected_scenario_id,document_id,input_kind,agent_selected_assembly_candidate_id) VALUES (?, ?, 'needs_review', NULL, ?, 1, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, mode, candidate_revision, extraction.model_dump_json(), json.dumps([item.model_dump(mode="json") for item in scenarios]), created_at, agent_selected_scenario_id, document_id, extraction.input_kind, agent_selected_assembly_candidate_id),
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
        return RunSnapshot(id=row["id"], mode=row["mode"], state=row["state"], reason_code=row["reason_code"], candidate_revision=row["candidate_revision"], result_revision=row["current_result_revision"], created_at=row["created_at"], agent_selected_scenario_id=row["agent_selected_scenario_id"], agent_selected_assembly_candidate_id=row["agent_selected_assembly_candidate_id"], document_id=row["document_id"], input_kind=row["input_kind"])

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
        if previous.input_semantics == "separated_part_views":
            return self._review_parts(run_id, previous, request)
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

    def save_table_cost_estimate(self, run_id: str, estimate: TableCostEstimate) -> None:
        result = self.get_result(run_id, estimate.result_revision)
        evaluated = result.evaluated_table_program
        if evaluated is None or evaluated.program_hash != estimate.program_hash:
            raise ValueError("table_program_revision_mismatch")
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO table_cost_estimates VALUES (?, ?, ?)", (run_id, estimate.result_revision, estimate.model_dump_json()))

    def get_table_cost_estimate(self, run_id: str, revision: int) -> TableCostEstimate:
        self.get_result(run_id, revision)
        with self._connect() as db:
            row = db.execute("SELECT payload FROM table_cost_estimates WHERE run_id=? AND revision=?", (run_id, revision)).fetchone()
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
            db.execute("INSERT OR REPLACE INTO table_drawing_manifests VALUES (?, ?, ?)", (run_id, manifest.result_revision, manifest.model_dump_json()))
            db.execute("DELETE FROM table_drawing_artifacts WHERE run_id=? AND revision=?", (run_id, manifest.result_revision))
            db.executemany(
                "INSERT INTO table_drawing_artifacts VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ((run_id, manifest.result_revision, item.sheet_id, item.format, manifest.program_hash, item.media_type, item.filename, item.content) for item in exports.artifacts),
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
