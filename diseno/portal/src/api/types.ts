/**
 * Tipos que reflejan el contrato Pydantic real de Vexplorer.
 * Fuente: backend/app/contratos/modelos.py (contrato parts-only 0.4) y backend/app/main.py.
 * Cada interfaz indica el modelo Python del que procede. Las tuplas Python se tipan como arrays.
 */

// ---- Sobre HTTP (main.py: _ok / _error) ----
export interface ApiEnvelope<T> {
  schema_version: "0.2.0";
  data: T;
}
export interface ApiErrorBody {
  schema_version: "0.2.0";
  error: { code: string; message: string; retryable: boolean };
}

export type RunMode = "live" | "geometry_only" | "recorded_replay";
export type InputKind = "mounted_views_legacy" | "separated_part_views";
export type Role = "side_panel" | "shelf" | "top_panel" | "base_panel" | "back_panel" | "door" | "divider" | "unknown";

// ---- GET /config (main.py: dict literal) ----
export interface AppConfig {
  provider: string;
  model: string | null;
  live_available: boolean;
  unavailable_reason: string | null;
  recorded_replay_available: boolean;
  modes: RunMode[];
  modality: string;
  limits: { max_model_calls: number; max_tool_calls: number; timeout_s: number };
  tools: { name: string; description: string }[];
  semantic: {
    available: boolean;
    provider: string;
    model: string;
    dimensions: number;
    unavailable_reason: string | null;
    offline_mode: string;
  };
}

// ---- POST /documents (main.py: dict literal) ----
export interface UploadedDocument {
  document_id: string;
  original_filename: string;
  size_bytes: number;
  sha256: string;
  source_kind: "uploaded";
}

// ---- Geometría (modelos.py) ----
/** Point2D */
export interface Point2D { x: number; y: number }
/** Point3D */
export interface Point3D { x: number; y: number; z: number }
/** Size3D */
export interface Size3D { x: number; y: number; z: number }
/** Bounds3D */
export interface Bounds3D { min: Point3D; max: Point3D }
/** Bounds2D */
export interface Bounds2D { min_x: number; min_y: number; max_x: number; max_y: number }

/** DrawingEntity */
export interface DrawingEntity { id: string; kind: string; layer: string; source_points: Point2D[]; points_mm: Point2D[] | null }
/** DrawingView */
export interface DrawingView { id: string; label: "FRONT" | "TOP" | "SIDE" | "UNKNOWN"; entity_ids: string[]; bounds_source: Bounds2D; bounds_mm: Bounds2D | null }
/** DrawingContour */
export interface DrawingContour { id: string; view_id: string; source_entity_ids: string[]; points_source: Point2D[]; points_mm: Point2D[] | null; closed: boolean }
/** DrawingText */
export interface DrawingText { id: string; source_entity_id: string; view_id: string; layer: string; text: string; position_source: Point2D; position_mm: Point2D | null }
/** DimensionGraphic */
export interface DimensionGraphic {
  id: string; dimension_id: string; source_entity_id: string; view_id: string; layer: string;
  display_text: string; raw_text: string;
  extension_start_a_source: Point2D; extension_start_a_mm: Point2D | null;
  extension_start_b_source: Point2D; extension_start_b_mm: Point2D | null;
  dimension_start_source: Point2D; dimension_start_mm: Point2D | null;
  dimension_end_source: Point2D; dimension_end_mm: Point2D | null;
  text_position_source: Point2D; text_position_mm: Point2D | null;
}
/** ObservedDimension */
export interface ObservedDimension { id: string; kind: "overall" | "annotation"; value_mm: number | null; source_entity_ids: string[]; evidence_ids: string[]; origin: "observed" | "derived"; view_id: string | null; graphic_id: string | null }
/** Evidence */
export interface Evidence { id: string; kind: "geometry" | "annotation" | "view_association"; source_entity_ids: string[]; description: string }
/** DrawingObservation */
export interface DrawingObservation { id: string; view_id: string; contour_ids: string[]; dimension_ids: string[] }

/** DrawingExtraction (GET /documents/{id}/drawing, GET /runs/{id}/drawing y /ledger) */
export interface DrawingExtraction {
  schema_version: "0.2.0";
  drawing_id: string;
  input_kind: InputKind;
  status: "ready" | "needs_review";
  source_unit: "mm" | "cm" | "m" | "in" | "unknown";
  unit_scale_to_mm: number | null;
  coordinate_unit: "mm" | "source";
  entities: DrawingEntity[];
  views: DrawingView[];
  contours: DrawingContour[];
  dimensions: ObservedDimension[];
  evidence: Evidence[];
  observations: DrawingObservation[];
  texts: DrawingText[];
  dimension_graphics: DimensionGraphic[];
  warnings: string[];
  synthetic: boolean;
}

// ---- Piezas separadas (contrato 0.4) ----
/** PartViewReference */
export interface PartViewReference { view_id: string; role: "FRONT" | "TOP" | "SIDE"; contour_ids: string[]; local_origin_source: Point2D; local_origin_mm: Point2D | null; local_bounds_source: Bounds2D; local_bounds_mm: Bounds2D | null }
/** ObservedPartDimension */
export interface ObservedPartDimension { value_mm: number | null; state: "observed" | "unknown" | "conflict"; origin: "observed"; measurement_ids: string[]; view_ids: string[]; evidence_ids: string[] }
/** PartDimensions */
export interface PartDimensions { length: ObservedPartDimension; width: ObservedPartDimension; thickness: ObservedPartDimension }
/** ObservedQuantity */
export interface ObservedQuantity { value: number | null; state: "observed" | "unknown" | "ambiguous"; evidence_ids: string[] }
/** SeparatedPartObservation */
export interface SeparatedPartObservation {
  id: string; part_key: string | null; association_basis: "explicit_key" | "unassociated" | "ambiguous";
  views: PartViewReference[]; dimensions: PartDimensions; quantity: ObservedQuantity;
  status: "complete" | "partial" | "ambiguous"; source_entity_ids: string[]; evidence_ids: string[]; warnings: string[];
}
/** SeparatedPartsExtraction */
export interface SeparatedPartsExtraction { schema_version: "0.4.0"; drawing_id: string; candidate_revision: string; input_kind: "separated_part_views"; observations: SeparatedPartObservation[]; warnings: string[] }
/** AssemblyPartUse */
export interface AssemblyPartUse {
  id: string; part_observation_id: string; role: Role; role_status: "hypothesis";
  source_quantity: number | null; allocated_quantity: number | null; occurrence_indices: number[];
  quantity_source: "observed_annotation" | "human_confirmed" | "unknown"; evidence_ids: string[];
}
/** AssemblyConstraint */
export interface AssemblyConstraint {
  id: string; kind: "equal_dimensions" | "exterior_from_parts" | "role_compatibility";
  operation: "equal" | "sum" | "difference" | "compatibility";
  dimension: "length" | "width" | "thickness" | "assembled_width" | "assembled_height" | "assembled_depth";
  operand_refs: string[]; result_mm: number | null; status: "pass" | "unknown" | "conflict"; tolerance_mm: number; evidence_ids: string[];
}
/** DerivedAssemblyDimension */
export interface DerivedAssemblyDimension { axis: "width" | "height" | "depth"; value_mm: number | null; state: "derived" | "unknown" | "conflict"; operand_refs: string[]; constraint_id: string | null }
/** AssemblyCandidate */
export interface AssemblyCandidate {
  id: string; family: "rectangular_shelving" | "unknown"; family_status: "hypothesis";
  layout: "between_sides" | "cap_sides" | "unknown"; layout_status: "hypothesis";
  uses: AssemblyPartUse[]; unassigned_part_observation_ids: string[]; constraints: AssemblyConstraint[];
  derived_dimensions: DerivedAssemblyDimension[]; unknown_fields: string[]; assumptions: string[]; evidence_ids: string[];
  state: "hypothesis"; needs_review: true;
}

// ---- Escenarios legacy (se reciben vacíos en parts-only) ----
/** ComponentProposal */
export interface ComponentProposal {
  id: string; label: string; role: Role; quantity: number | null; length_mm: number | null; width_mm: number | null; thickness_mm: number | null;
  length_derivation: string; length_basis_mm: number | null; source_observation_ids: string[]; source_contour_ids: string[];
  source_entity_ids: string[]; evidence_ids: string[]; source_part_observation_ids: string[]; assumptions: string[]; information_class: "hypothesis";
}
/** DecompositionScenario */
export interface DecompositionScenario { id: string; title: string; components: ComponentProposal[]; assumptions: string[]; incompatible_with: string[]; state: "hypothesis" }

// ---- Revisión ----
export type FieldState = "observed" | "calculated" | "confirmed" | "unknown";
/** ReviewDecision */
export interface ReviewDecision {
  proposal_id: string; action: "confirm" | "reject"; role?: Role; quantity?: number | null;
  length_mm?: number | null; width_mm?: number | null; thickness_mm?: number | null;
  material?: string | null; finish?: string | null; notes: string;
}
/** ReviewRequest (POST /runs/{id}/reviews) */
export interface ReviewRequest {
  base_result_revision: number; reviewer_name: string; decisions?: ReviewDecision[];
  scenario_id?: string | null; confirmed_thickness_mm?: number | null;
  material?: string | null; finish?: string | null; notes?: string | null; assembly_candidate_id?: string | null;
}
/** ResolvedPiece */
export interface ResolvedPiece {
  id: string; proposal_id: string; label: string; role: string; quantity: number | null;
  length_mm: number | null; width_mm: number | null; thickness_mm: number | null; material: string | null; finish: string | null;
  source_observation_ids: string[]; source_contour_ids: string[]; evidence_ids: string[]; source_part_observation_ids: string[];
  human_confirmation: string; field_states: Record<string, FieldState>;
}
/** HumanReview */
export interface HumanReview { reviewer_name: string; reason: string; timestamp: string; selected_scenario_id: string | null; selected_assembly_candidate_id: string | null }
/** Result */
export interface Result {
  schema_version: "0.2.0"; run_id: string; result_revision: number; state: "completed" | "needs_review";
  scenarios: DecompositionScenario[]; pieces: ResolvedPiece[]; rejected_proposal_ids: string[]; created_at: string;
  review: HumanReview | null; agent_selected_scenario_id: string | null; input_semantics: InputKind;
  part_analysis: SeparatedPartsExtraction | null; assembly_candidates: AssemblyCandidate[]; selected_assembly_candidate_id: string | null;
}
/** RunSnapshot */
export interface RunSnapshot {
  schema_version: "0.2.0"; id: string; mode: "live" | "geometry_only";
  state: "completed" | "needs_review" | "failed" | "cancelled" | "timed_out"; reason_code: string | null;
  candidate_revision: string; result_revision: number | null; created_at: string;
  agent_selected_scenario_id: string | null; agent_selected_assembly_candidate_id: string | null;
  document_id: string | null; input_kind: InputKind;
}
/** POST /runs → 201 */
export interface CreatedRun { run: RunSnapshot; result: Result }
/** GET /runs/{id} */
export interface RunDetail { run: RunSnapshot; result: Result; estimate: Estimate | null }
/** GET /runs/{id}/parts */
export interface PartsView { part_analysis: SeparatedPartsExtraction; assembly_candidates: AssemblyCandidate[]; selected_assembly_candidate_id: string | null }

// ---- Escena 3D ----
/** SceneObject */
export interface SceneObject {
  id: string; piece_id: string; proposal_id: string; role: string; label: string; occurrence_index: number;
  position_mm: Point3D; dimensions_mm: Size3D; bbox_mm: Bounds3D; source_contour_ids: string[]; evidence_ids: string[];
  placement_basis: string; part_observation_id: string | null; placement_status: "hypothesis" | "human_selected"; placement_constraint_ids: string[];
}
/** ReconstructionScene */
export interface ReconstructionScene {
  schema_version: "0.3.0"; run_id: string; result_revision: number; state: "ready" | "incomplete" | "unavailable";
  selected_scenario_id: string | null; coordinate_system: string; objects: SceneObject[]; warnings: string[]; assumptions: string[]; collision_status: "not_evaluated";
}

// ---- Explicaciones ----
/** FormulaExplanation */
export interface FormulaExplanation { field: string; expression: string; operands_mm: Record<string, number>; result_mm: number }
/** PieceExplanation */
export interface PieceExplanation {
  piece_id: string; proposal_id: string; role: string; source_entity_ids: string[]; source_contour_ids: string[]; evidence_ids: string[];
  dimension_ids: string[]; measurements: Record<string, number | null>; formulas: FormulaExplanation[]; premises: string[]; unknown_fields: string[];
  field_states: Record<string, "observed" | "calculated" | "confirmed" | "hypothesis" | "unknown">;
}
/** ExplanationBundle */
export interface ExplanationBundle { schema_version: "0.3.0"; run_id: string; result_revision: number; pieces: PieceExplanation[]; warnings: string[] }

// ---- Biblioteca y similitud ----
/** DescriptorDimensions */
export interface DescriptorDimensions { width_mm: number | null; depth_mm: number | null; height_mm: number | null }
/** RoleQuantity */
export interface RoleQuantity { role: string; quantity: number | null }
/** DescriptorPartFeature */
export interface DescriptorPartFeature {
  length_mm: number | null; width_mm: number | null; thickness_mm: number | null; quantity: number | null;
  unknown_fields: string[]; field_states: Record<string, "observed" | "confirmed" | "unknown">;
}
/** FurnitureDescriptor (v1) y FurnitureDescriptorV2 */
export interface FurnitureDescriptor {
  descriptor_version: "furniture-v1" | "furniture-v2"; family: "rectangular_shelving" | "unknown"; dimensions: DescriptorDimensions;
  roles: RoleQuantity[]; structure: "top_base_between_sides" | "top_base_cap_sides" | "unknown"; material: string | null; finish: string | null;
  thicknesses_mm?: number[]; classification_status?: "hypothesis" | "confirmed"; part_features?: DescriptorPartFeature[]; unknown_fields: string[];
}
/** EmbeddingMetadata */
export interface EmbeddingMetadata { provider: "openai"; model: string; dimensions: number; descriptor_version: string; cache_key: string; status: "generated" | "cache" }
/** LibraryItem */
export interface LibraryItem {
  schema_version: "0.3.0"; id: string; run_id: string; result_revision: number; label: string; descriptor: FurnitureDescriptor;
  descriptor_fingerprint: string; created_at: string; embedding: EmbeddingMetadata | null;
}
/** SimilarityDifference */
export interface SimilarityDifference { field: string; query_value: string; candidate_value: string }
/** SimilarityMatch */
export interface SimilarityMatch {
  library_item_id: string; run_id: string; result_revision: number; method: "geometric" | "semantic"; score: number;
  score_kind: "geometric_similarity" | "cosine_similarity"; score_components: Record<string, number>; differences: SimilarityDifference[]; embedding: EmbeddingMetadata | null;
}
/** SimilarityGroup */
export interface SimilarityGroup { id: string; member_ids: string[]; method: "geometric" | "semantic"; score_kind: string; threshold: number; explanation: string }

export interface LibrarySaveRequest { result_revision: number; label: string; embedding_mode: "offline" | "openai" }
export interface SimilarityRequest { result_revision: number; mode: "geometric" | "semantic"; limit?: number }
export interface GroupRequest { mode: "geometric" | "semantic"; threshold?: number }

// ---- Histórico y estimación ----
/** Comparable */
export interface Comparable {
  id: string; name: string; family: string; width_mm: number; depth_mm: number; height_mm: number; material: string; finish: string;
  score: number; differences: string[]; fixed_cost_eur: number; material_cost_eur: number; reference_area_mm2: number; hours: number | null; synthetic: true;
}
/** CostConcept */
export interface CostConcept { id: string; label: string; cost_type: "fixed" | "material" | "labor" | "finish"; base_amount: number; factor: number; amount: number; explanation: string; comparable_id: string }
/** Estimate */
export interface Estimate {
  schema_version: "0.2.0"; run_id: string; result_revision: number; currency: "EUR"; concepts: CostConcept[]; total: number;
  hours: number | null; assumptions: string[]; comparable_ids: string[]; synthetic: true;
}

// ---- Eventos (GET /runs/{id}/events, text/event-stream finito) ----
export type RunEventType =
  | "run_state_changed" | "tool_completed" | "result_committed" | "run_finished"
  | "human_review_committed" | "library_item_saved" | "estimate_committed";
export interface RunEvent {
  schema_version: "0.2.0";
  run_id: string;
  sequence: number;
  event_type: RunEventType | string;
  /** `timestamp` viaja dentro de `data` en el backend real. */
  data: Record<string, unknown> & { timestamp?: string };
}
