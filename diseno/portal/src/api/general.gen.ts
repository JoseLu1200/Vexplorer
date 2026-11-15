/* Archivo generado por scripts/gen_general_types.py. No editar a mano. */
/* Fuente: backend/app/contratos/modelos.py y backend/app/reconstruction3d de Vexplorer. */
/* Respuestas en modo serialización (todos los campos presentes); peticiones en modo validación. */

/** AssemblyProposal */
export interface AssemblyProposal {
  status: "proposed" | "insufficient_evidence" | "unsupported";
  intended_use: string;
  unit: "mm" | "relative";
  components: Component[];
  assumptions: string[];
  missing_information: string[];
  functional_notes: string[];
}

/** Bounds2D */
export interface Bounds2D {
  min_x: number;
  min_y: number;
  max_x: number;
  max_y: number;
}

/** Bounds3D */
export interface Bounds3D {
  min: Point3D;
  max: Point3D;
}

/** CircularGeometry */
export interface CircularGeometry {
  kind: "circle" | "arc";
  center_source: Point2D;
  center_mm: Point2D | null;
  radius_source: number;
  radius_mm: number | null;
  start_angle_deg: number | null;
  end_angle_deg: number | null;
}

/** Component */
export interface Component {
  id: string;
  label: string;
  size_mm: number[];
  origin_mm: number[];
  source_refs: string[];
  assumptions: string[];
}

/** DimensionGraphic */
export interface DimensionGraphic {
  id: string;
  dimension_id: string;
  source_entity_id: string;
  view_id: string;
  layer: string;
  display_text: string;
  raw_text: string;
  extension_start_a_source: Point2D;
  extension_start_a_mm: Point2D | null;
  extension_start_b_source: Point2D;
  extension_start_b_mm: Point2D | null;
  dimension_start_source: Point2D;
  dimension_start_mm: Point2D | null;
  dimension_end_source: Point2D;
  dimension_end_mm: Point2D | null;
  text_position_source: Point2D;
  text_position_mm: Point2D | null;
}

/** DrawingContour */
export interface DrawingContour {
  id: string;
  view_id: string;
  source_entity_ids: string[];
  points_source: Point2D[];
  points_mm: Point2D[] | null;
  closed: boolean;
}

/** DrawingEntity */
export interface DrawingEntity {
  id: string;
  kind: string;
  layer: string;
  source_points: Point2D[];
  points_mm: Point2D[] | null;
  linetype: string | null;
  circular: CircularGeometry | null;
}

/** DrawingExtraction */
export interface DrawingExtraction {
  schema_version: "0.2.0";
  drawing_id: string;
  input_kind: "mounted_views_legacy" | "separated_part_views" | "mounted_orthographic_views" | "general_furniture";
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

/** DrawingObservation */
export interface DrawingObservation {
  id: string;
  view_id: string;
  contour_ids: string[];
  dimension_ids: string[];
}

/** DrawingText */
export interface DrawingText {
  id: string;
  source_entity_id: string;
  view_id: string;
  layer: string;
  text: string;
  position_source: Point2D;
  position_mm: Point2D | null;
}

/** DrawingView */
export interface DrawingView {
  id: string;
  label: "FRONT" | "TOP" | "SIDE" | "UNKNOWN";
  entity_ids: string[];
  bounds_source: Bounds2D;
  bounds_mm: Bounds2D | null;
}

/** Evidence */
export interface Evidence {
  id: string;
  kind: "geometry" | "annotation" | "view_association";
  source_entity_ids: string[];
  description: string;
}

/** GeneralAssemblyAlternative */
export interface GeneralAssemblyAlternative {
  alternative_id: string;
  relations: GeneralAssemblyRelation[];
  premise_ids: string[];
}

/** GeneralAssemblyAttempt */
export interface GeneralAssemblyAttempt {
  schema_version: "assembly-attempt-1";
  run_id: string;
  proposal_revision: number;
  review_revision: number;
  assembly_revision: number;
  attempt_index: number;
  candidate: GeneralAssemblyCandidate | null;
  report: GeneralAssemblyValidationReport;
  model: string;
  policy_version: string;
  sources: string[];
  trace: GeneralAssemblyTraceEvent[];
}

/** GeneralAssemblyCandidate */
export interface GeneralAssemblyCandidate {
  schema_version: "assembly-1";
  run_id: string;
  proposal_revision: number;
  review_revision: number;
  assembly_revision: number;
  candidate_id: string;
  alternative_id: string;
  frames: GeneralAssemblyFrame[];
  placements: GeneralAssemblyPlacementHypothesis[];
  penetration_hypotheses: GeneralAssemblyPenetrationHypothesis[];
  sources: string[];
}

/** GeneralAssemblyFrame */
export interface GeneralAssemblyFrame {
  id: string;
  region_id: string;
  view_id: string;
  horizontal_axis: "+x" | "-x" | "+y" | "-y" | "+z" | "-z";
  vertical_axis: "+x" | "-x" | "+y" | "-y" | "+z" | "-z";
  origin_corner: "lower_left" | "lower_right" | "upper_left" | "upper_right";
}

/** GeneralAssemblyOrientation */
export interface GeneralAssemblyOrientation {
  length_axis: "+x" | "-x" | "+y" | "-y" | "+z" | "-z";
  width_axis: "+x" | "-x" | "+y" | "-y" | "+z" | "-z";
  thickness_axis: "+x" | "-x" | "+y" | "-y" | "+z" | "-z";
}

/** GeneralAssemblyPenetrationHypothesis */
export interface GeneralAssemblyPenetrationHypothesis {
  occurrence_ids: [string, string];
  kind: "projected_overlap_machining_unverified";
  source_refs: string[];
}

/** GeneralAssemblyPlacement */
export interface GeneralAssemblyPlacement {
  occurrence_id: string;
  occurrence_index: number;
  component_id: string;
  position_mm: Point3D;
  size_mm: Size3D;
  orientation: GeneralAssemblyOrientation;
  source_refs: string[];
}

/** GeneralAssemblyPlacementHypothesis */
export interface GeneralAssemblyPlacementHypothesis {
  occurrence_id: string;
  occurrence_index: number;
  component_id: string;
  orientation: GeneralAssemblyOrientation;
  projections: GeneralAssemblyProjection[];
}

/** GeneralAssemblyProjection */
export interface GeneralAssemblyProjection {
  frame_id: string;
  contour_id: string;
  evidence_ids: string[];
  occlusion_ambiguity_id: string | null;
}

/** GeneralAssemblyRelation */
export interface GeneralAssemblyRelation {
  subject_component_id: string;
  relation: "supported_by" | "fixed_to" | "attached_to" | "contained_by" | "aligned_with" | "adjacent_to" | "hinged_to" | "unknown";
  object_component_id: string;
  state: "hypothesis" | "unknown" | "conflict";
  premise_ids: string[];
  source_refs: string[];
}

/** GeneralAssemblyState */
export interface GeneralAssemblyState {
  schema_version: "assembly-state-1";
  run_id: string;
  proposal_revision: number;
  review_revision: number;
  assembly_revision: number;
  status: "accepted" | "ambiguous" | "incomplete" | "rejected";
  current: GeneralAssemblyAttempt;
  accepted_alternatives: GeneralAssemblyAttempt[];
  ambiguous: boolean;
}

/** GeneralAssemblyTraceEvent */
export interface GeneralAssemblyTraceEvent {
  sequence: number;
  kind: "inspect" | "evaluate" | "repair" | "final";
  summary: string;
}

/** GeneralAssemblyValidationIssue */
export interface GeneralAssemblyValidationIssue {
  code: string;
  severity: "error" | "warning";
  message: string;
  occurrence_ids: string[];
  source_refs: string[];
}

/** GeneralAssemblyValidationReport */
export interface GeneralAssemblyValidationReport {
  schema_version: "assembly-report-1";
  status: "accepted" | "rejected" | "incomplete";
  issues: GeneralAssemblyValidationIssue[];
  placements: GeneralAssemblyPlacement[];
  scene: GeneralScene | null;
  global_bounds_mm: Bounds3D | null;
  max_penetration_mm: number;
}

/** GeneralAutoReviewCheck */
export interface GeneralAutoReviewCheck {
  id: string;
  kind: "geometry_match" | "cross_view_identity" | "duplicate_scan" | "shared_projection_support" | "quantity_basis" | "dimension_binding" | "visual_consistency";
  outcome: "pass" | "fail" | "unknown";
  method: "deterministic" | "model_visual";
  target_refs: string[];
  source_refs: string[];
  summary: string;
}

/** GeneralBinding */
export interface GeneralBinding {
  id: string;
  operation: "copy" | "add" | "subtract" | "scale_rational";
  rational_numerator: number;
  rational_denominator: number;
  operand_refs: string[];
}

/** GeneralBomRow */
export interface GeneralBomRow {
  component_id: string;
  label: string;
  kind: string;
  role: string;
  occurrence_ids: string[];
  scenario_occurrence_ids: string[];
  occurrence_status: "confirmed" | "provisional" | "unknown";
  quantity: GeneralQuantity;
  length: GeneralValue;
  width: GeneralValue;
  thickness: GeneralValue;
  material: GeneralTextValue;
  finish: GeneralTextValue;
  source_view_ids: string[];
  source_observation_ids: string[];
  source_contour_ids: string[];
  source_evidence_ids: string[];
  source_dimension_ids: string[];
  source_document_refs: string[];
  machine_field_reviews: GeneralDerivedFieldReview[];
}

/** GeneralComponentProposal */
export interface GeneralComponentProposal {
  id: string;
  label: string;
  kind: "panel" | "linear_member" | "hardware" | "unknown";
  role: string;
  length_binding_id: string | null;
  width_binding_id: string | null;
  thickness_binding_id: string | null;
  quantity: GeneralQuantity;
  premise_ids: string[];
  source_view_ids: string[];
  source_observation_ids: string[];
  source_contour_ids: string[];
  source_evidence_ids: string[];
  source_dimension_ids: string[];
  source_document_refs: string[];
  assumptions: string[];
  unknown_fields: string[];
  scenario_id: string;
  necessity: "visible" | "deduced_required" | "estimated_required";
  geometry: GeneralPieceGeometry;
  construction_parameter_ids: string[];
  detail_ids: string[];
  quantity_basis_refs: string[];
}

/** GeneralComponentReview */
export interface GeneralComponentReview {
  id: string;
  label: string;
  kind: "panel" | "linear_member" | "hardware" | "unknown";
  role: string;
  length: GeneralValue;
  width: GeneralValue;
  thickness: GeneralValue;
  quantity: GeneralQuantity;
  material: GeneralTextValue;
  finish: GeneralTextValue;
  replaces_component_ids: string[];
  source_view_ids: string[];
  source_observation_ids: string[];
  source_contour_ids: string[];
  source_evidence_ids: string[];
  source_dimension_ids: string[];
  source_document_refs: string[];
  assumptions: string[];
  unknown_fields: string[];
  scenario_id: string;
  necessity: "visible" | "deduced_required" | "estimated_required";
  geometry: GeneralPieceGeometry;
  construction_parameter_ids: string[];
  detail_ids: string[];
  quantity_basis_refs: string[];
}

/** GeneralConstraintResult */
export interface GeneralConstraintResult {
  constraint_id: string;
  status: "pass" | "fail" | "unknown";
  left_range_mm: GeneralDimensionRange | null;
  right_range_mm: GeneralDimensionRange | null;
  residual_mm: number | null;
}

/** GeneralConstructionConstraint */
export interface GeneralConstructionConstraint {
  id: string;
  kind: "overall_closure" | "clearance" | "repeated_equal" | "fit" | "sum_equals" | "equal" | "greater_equal";
  left_refs: string[];
  right_refs: string[];
  tolerance_mm: number;
  severity: "error" | "warning";
  source_refs: string[];
  rationale: string;
}

/** GeneralConstructionDecision */
export interface GeneralConstructionDecision {
  id: string;
  category: "dimension" | "component" | "quantity" | "geometry" | "joint" | "edge" | "machining" | "assembly";
  summary: string;
  target_refs: string[];
  basis_refs: string[];
  alternatives: string[];
  rationale: string;
  impact: "high" | "medium" | "low";
}

/** GeneralConstructionDetail */
export interface GeneralConstructionDetail {
  id: string;
  kind: "joint" | "edge" | "bore" | "groove" | "rabbet" | "fastener" | "section" | "other";
  component_ids: string[];
  parameter_refs: string[];
  quantity: number;
  state: "deduced" | "estimated";
  source_refs: string[];
  assumption_refs: string[];
  rationale: string;
  geometry: GeneralConstructionDetailGeometry | null;
}

/** GeneralConstructionDetailGeometry */
export interface GeneralConstructionDetailGeometry {
  kind: "point" | "line" | "polyline" | "circle";
  points_mm: Point2D[];
  dimension_refs: string[];
}

/** GeneralConstructionDimension */
export interface GeneralConstructionDimension {
  value_mm: number | null;
  range_mm: GeneralDimensionRange | null;
  state: "observed" | "deduced" | "estimated" | "unknown" | "conflict";
  review_status: "accepted" | "rejected" | "conflict" | "abstained" | "unreviewed";
  method: string | null;
  formula: string | null;
  operand_refs: string[];
  source_refs: string[];
  assumption_refs: string[];
  explanation: string;
}

/** GeneralConstructionIssue */
export interface GeneralConstructionIssue {
  severity: "error" | "warning";
  code: string;
  message: string;
  target_refs: string[];
}

/** GeneralConstructionParameter */
export interface GeneralConstructionParameter {
  id: string;
  label: string;
  basis: "observed" | "deduced" | "estimated";
  nominal_mm: number | null;
  range_mm: GeneralDimensionRange | null;
  method: "observed_copy" | "arithmetic" | "fit" | "symmetry" | "equal_spacing" | "proportion" | "construction_assumption";
  binding_id: string | null;
  source_refs: string[];
  assumption_refs: string[];
  rationale: string;
}

/** GeneralConstructionPiece */
export interface GeneralConstructionPiece {
  piece_id: string;
  component_id: string;
  scenario_id: string;
  label: string;
  role: string;
  quantity: GeneralConstructionQuantity;
  occurrence_ids: string[];
  scenario_occurrence_ids: string[];
  geometry: GeneralPieceGeometry;
  length: GeneralConstructionDimension;
  width: GeneralConstructionDimension;
  thickness: GeneralConstructionDimension;
  detail_ids: string[];
  source_refs: string[];
  sheet_ids: string[];
}

/** GeneralConstructionPlan */
export interface GeneralConstructionPlan {
  run_id: string;
  proposal_revision: number;
  review_revision: number;
  basis_revision: string;
  scenario_id: string;
  summary: GeneralConstructionSummary;
  pieces: GeneralConstructionPiece[];
  placements: GeneralPiecePlacement[];
  details: GeneralConstructionDetail[];
  decisions: GeneralConstructionDecision[];
  warnings: GeneralConstructionWarning[];
  sheets: GeneralSheetPlan[];
  authority: "provisional_not_manufacturing";
}

/** GeneralConstructionQuantity */
export interface GeneralConstructionQuantity {
  value: number | null;
  min_value: number | null;
  max_value: number | null;
  state: "observed" | "deduced" | "estimated" | "unknown" | "conflict";
  review_status: "accepted" | "rejected" | "conflict" | "abstained" | "unreviewed";
  method: string | null;
  source_refs: string[];
  assumption_refs: string[];
  explanation: string;
}

/** GeneralConstructionSummary */
export interface GeneralConstructionSummary {
  label: string;
  component_count: number;
  occurrence_count: number;
  source_refs: string[];
  top_decision_ids: string[];
  warnings: GeneralConstructionWarning[];
}

/** GeneralConstructionValidation */
export interface GeneralConstructionValidation {
  status: "valid" | "invalid" | "incomplete";
  parameter_order: string[];
  max_depth: number;
  constraint_results: GeneralConstraintResult[];
  issues: GeneralConstructionIssue[];
}

/** GeneralConstructionWarning */
export interface GeneralConstructionWarning {
  severity: "error" | "warning" | "info";
  code: string;
  message: string;
  component_refs: string[];
  field_refs: string[];
  consequence: "blocks_fabrication" | "provisional_only";
}

/** GeneralCostBasis */
export interface GeneralCostBasis {
  status: "complete" | "partial" | "unavailable";
  contributors: GeneralCostBasisContributor[];
  missing_data: string[];
}

/** GeneralCostBasisContributor */
export interface GeneralCostBasisContributor {
  component_id: string;
  occurrence_ids: string[];
  area_m2: number | null;
  volume_m3: number | null;
  material: GeneralTextValue;
  finish: GeneralTextValue;
  missing_data: string[];
}

/** GeneralDerivedArtifact */
export interface GeneralDerivedArtifact {
  id: string;
  kind: "bom_csv" | "bom_json" | "drawing_svg" | "drawing_dxf" | "construction_overview_svg" | "construction_overview_dxf" | "piece_sheet_svg" | "piece_sheet_dxf";
  status: "ready" | "incomplete";
  review_revision: number;
  filename: string;
  media_type: string;
  incomplete_reasons: string[];
  sheet_id: string | null;
  component_id: string | null;
  content: string;
}

/** GeneralDerivedEnvelope */
export interface GeneralDerivedEnvelope {
  schema_version: "0.6.0";
  data: GeneralDerivedResponse;
}

/** GeneralDerivedFieldReview */
export interface GeneralDerivedFieldReview {
  field: "length" | "width" | "thickness" | "quantity" | "material" | "finish";
  target_ref: string;
  status: "accepted" | "rejected" | "conflict" | "abstained" | "unreviewed";
  check_ids: string[];
  check_summaries: string[];
  source_refs: string[];
}

/** GeneralDerivedPackage */
export interface GeneralDerivedPackage {
  schema_version: "0.6.0";
  run_id: string;
  proposal_revision: number;
  review_revision: number;
  status: "ready" | "incomplete";
  bom_rows: GeneralBomRow[];
  artifacts: GeneralDerivedArtifact[];
  scene: GeneralScene;
  cost_basis: GeneralCostBasis;
  construction: GeneralConstructionPlan | null;
}

/** GeneralDerivedResponse */
export interface GeneralDerivedResponse {
  package: GeneralDerivedPackage;
  historical_target: GeneralHistoricalTarget;
}

/** GeneralDimensionRange */
export interface GeneralDimensionRange {
  min_mm: number;
  max_mm: number;
}

/** GeneralDraftComponent */
export interface GeneralDraftComponent {
  id: string;
  label: string;
  kind: "panel" | "linear_member" | "hardware" | "unknown";
  role: string;
  length: GeneralValue;
  width: GeneralValue;
  thickness: GeneralValue;
  quantity: GeneralQuantity;
  premise_ids: string[];
  source_view_ids: string[];
  source_observation_ids: string[];
  source_contour_ids: string[];
  source_evidence_ids: string[];
  source_dimension_ids: string[];
  source_document_refs: string[];
  assumptions: string[];
  unknown_fields: string[];
  scenario_id: string;
  necessity: "visible" | "deduced_required" | "estimated_required";
  geometry: GeneralPieceGeometry;
  construction_parameter_ids: string[];
  detail_ids: string[];
  quantity_basis_refs: string[];
}

/** GeneralEvidenceDisposition */
export interface GeneralEvidenceDisposition {
  candidate_region_id: string;
  kind: "assigned" | "duplicate_projection" | "shared_projection_support" | "nonmaterial" | "unresolved";
  component_id: string | null;
  support_component_ids: string[];
  duplicate_of_region_id: string | null;
  reason_code: "hole" | "cutout" | "rabbet" | "groove" | "annotation" | "drawing_frame" | "void" | "other_unresolved" | null;
  source_refs: string[];
  rationale: string;
}

/** GeneralFurnitureDraft */
export interface GeneralFurnitureDraft {
  schema_version: "0.6.0";
  proposal_id: string;
  drawing_id: string;
  ledger_revision: string;
  components: GeneralDraftComponent[];
  premises: GeneralPremise[];
  assumptions: string[];
  construction_scenario_id: string;
  construction_parameters: GeneralResolvedConstructionParameter[];
  construction_constraints: GeneralConstructionConstraint[];
  construction_details: GeneralConstructionDetail[];
  construction_decisions: GeneralConstructionDecision[];
  construction_placements: GeneralPiecePlacement[];
  evidence_dispositions: GeneralEvidenceDisposition[];
  assembly_relations: GeneralAssemblyRelation[];
  assembly_alternatives: GeneralAssemblyAlternative[];
  status: "needs_review";
}

/** GeneralFurnitureEnvelope */
export interface GeneralFurnitureEnvelope {
  schema_version: "0.6.0";
  data: GeneralFurnitureRecord;
}

/** GeneralFurnitureProposal */
export interface GeneralFurnitureProposal {
  schema_version: "0.6.0";
  id: string;
  drawing_id: string;
  ledger_revision: string;
  proposal_origin: "native_tool" | "human";
  bindings: GeneralBinding[];
  components: GeneralComponentProposal[];
  premises: GeneralPremise[];
  assumptions: string[];
  construction_scenario_id: string;
  construction_parameters: GeneralConstructionParameter[];
  construction_constraints: GeneralConstructionConstraint[];
  construction_details: GeneralConstructionDetail[];
  construction_decisions: GeneralConstructionDecision[];
  construction_placements: GeneralPiecePlacement[];
  evidence_dispositions: GeneralEvidenceDisposition[];
  assembly_relations: GeneralAssemblyRelation[];
  assembly_alternatives: GeneralAssemblyAlternative[];
}

/** GeneralFurnitureRecord */
export interface GeneralFurnitureRecord {
  run_id: string;
  status: "needs_review" | "reviewed_incomplete" | "approved";
  proposal_revision: number;
  review_revision: number;
  proposal: GeneralFurnitureProposal;
  draft: GeneralFurnitureDraft;
  review: GeneralFurnitureReview | null;
}

/** GeneralFurnitureReview */
export interface GeneralFurnitureReview {
  schema_version: "0.6.0";
  run_id: string;
  proposal_id: string;
  proposal_revision: number;
  review_revision: number;
  reviewer_name: string;
  reviewer_kind: "human" | "machine";
  machine_provenance: GeneralMachineProvenance | null;
  reason: string;
  reviewed_at: string;
  operations: GeneralReviewOperation[];
  components: GeneralComponentReview[];
  occurrences: GeneralOccurrence[];
  scenario_occurrences: GeneralScenarioOccurrence[];
  machine_checks: GeneralAutoReviewCheck[];
  machine_field_reviews: GeneralMachineFieldReview[];
  evidence_dispositions: GeneralEvidenceDisposition[];
  auto_review_status: "accepted" | "incomplete" | "conflict" | "abstained" | null;
  furniture_quantity: GeneralQuantity;
  currency: string | null;
  required_cost_scope: string[];
  required_hours_scope: string[];
  construction_scenario_id: string;
  construction_parameters: GeneralResolvedConstructionParameter[];
  construction_constraints: GeneralConstructionConstraint[];
  construction_details: GeneralConstructionDetail[];
  construction_decisions: GeneralConstructionDecision[];
  construction_validation: GeneralConstructionValidation | null;
  construction_placements: GeneralPiecePlacement[];
  status: "approved" | "reviewed_incomplete";
}

/** GeneralHistoricalTarget */
export interface GeneralHistoricalTarget {
  family: string | null;
  width_mm: number | null;
  depth_mm: number | null;
  height_mm: number | null;
  area_mm2: number | null;
  length_mm: number | null;
  volume_mm3: number | null;
  quantity: number | null;
  material: string | null;
  finish: string | null;
  currency: string | null;
  required_cost_scope: string[];
  required_hours_scope: string[];
  basis_revision: string;
  exclude_project_id: string | null;
  exclude_record_ids: string[];
}

/** GeneralMachineFieldReview */
export interface GeneralMachineFieldReview {
  target_ref: string;
  status: "accepted" | "rejected" | "conflict" | "abstained";
  check_ids: string[];
}

/** GeneralMachineProvenance */
export interface GeneralMachineProvenance {
  model: string;
  policy_version: string;
  response_ids: string[];
  review_relation: "separate_model" | "self_review";
}

/** GeneralOccurrence */
export interface GeneralOccurrence {
  id: string;
  component_id: string;
  occurrence_index: number;
}

/** GeneralPieceGeometry */
export interface GeneralPieceGeometry {
  shape_kind: "rectangle" | "linear" | "custom_contour" | "hardware" | "unknown";
  source_contour_ids: string[];
  basis_refs: string[];
  rationale: string;
}

/** GeneralPiecePlacement */
export interface GeneralPiecePlacement {
  occurrence_ref: string;
  piece_id: string;
  x_mm: number;
  y_mm: number;
  rotation_deg: number;
  state: "deduced" | "estimated";
  source_refs: string[];
  assumption_refs: string[];
}

/** GeneralPremise */
export interface GeneralPremise {
  id: string;
  description: string;
  required: boolean;
  blocking: boolean;
}

/** GeneralQuantity */
export interface GeneralQuantity {
  value: number | null;
  state: "observed" | "derived" | "deduced" | "estimated" | "hypothesis" | "confirmed" | "unknown" | "conflict";
  dependency_refs: string[];
  evidence_ids: string[];
}

/** GeneralResolvedConstructionParameter */
export interface GeneralResolvedConstructionParameter {
  id: string;
  label: string;
  nominal_mm: number;
  range_mm: GeneralDimensionRange;
  state: "observed" | "deduced" | "estimated";
  method: string;
  binding_id: string | null;
  formula: string | null;
  dependency_refs: string[];
  source_refs: string[];
  assumption_refs: string[];
  rationale: string;
}

/** GeneralReviewOperation */
export interface GeneralReviewOperation {
  kind: "replace" | "split" | "merge" | "drop";
  source_component_ids: string[];
  result_component_ids: string[];
  reason: string;
}

/** GeneralScenarioOccurrence */
export interface GeneralScenarioOccurrence {
  id: string;
  component_id: string;
  occurrence_index: number;
  scenario_id: string;
  quantity_target_ref: string;
  check_ids: string[];
  premise_refs: string[];
  source_refs: string[];
  state: "provisional";
}

/** GeneralScene */
export interface GeneralScene {
  status: "schematic_incomplete" | "schematic_ready" | "unavailable" | "mounted_hypothesis";
  items: GeneralSceneItem[];
  warnings: string[];
}

/** GeneralSceneItem */
export interface GeneralSceneItem {
  id: string;
  component_id: string;
  occurrence_ids: string[];
  scenario_occurrence_ids: string[];
  occurrence_status: "confirmed" | "provisional" | "unknown";
  length: GeneralValue;
  width: GeneralValue;
  thickness: GeneralValue;
  position_mm: Point3D | null;
  size_mm: Size3D | null;
  occurrence_id: string | null;
  occurrence_index: number | null;
  orientation: GeneralAssemblyOrientation | null;
  status: "schematic_unplaced" | "unavailable" | "placed_hypothesis";
}

/** GeneralSheetPlan */
export interface GeneralSheetPlan {
  sheet_id: string;
  kind: "assembly" | "piece";
  piece_id: string | null;
  title: string;
  primitives: GeneralSheetPrimitive[];
  warnings: GeneralConstructionWarning[];
}

/** GeneralSheetPrimitive */
export interface GeneralSheetPrimitive {
  kind: "line" | "polyline" | "circle" | "arc" | "dimension" | "text" | "detail_callout";
  points_mm: Point2D[];
  text: string | null;
  state: "observed" | "deduced" | "estimated" | "unknown";
  source_refs: string[];
}

/** GeneralTextValue */
export interface GeneralTextValue {
  value: string | null;
  state: "observed" | "derived" | "deduced" | "estimated" | "hypothesis" | "confirmed" | "unknown" | "conflict";
  dependency_refs: string[];
  evidence_ids: string[];
}

/** GeneralValue */
export interface GeneralValue {
  value_mm: number | null;
  unit: "mm";
  state: "observed" | "derived" | "deduced" | "estimated" | "hypothesis" | "confirmed" | "unknown" | "conflict";
  dependency_refs: string[];
  evidence_ids: string[];
  dimension_ids: string[];
  range_mm: GeneralDimensionRange | null;
  method: string | null;
  formula: string | null;
  assumption_refs: string[];
}

/** ObservedDimension */
export interface ObservedDimension {
  id: string;
  kind: "overall" | "annotation";
  value_mm: number | null;
  source_entity_ids: string[];
  evidence_ids: string[];
  origin: "observed" | "derived";
  view_id: string | null;
  graphic_id: string | null;
}

/** Point2D */
export interface Point2D {
  x: number;
  y: number;
}

/** Point3D */
export interface Point3D {
  x: number;
  y: number;
  z: number;
}

/** ReconstructionScene */
export interface ReconstructionScene {
  schema_version: "0.3.0";
  run_id: string;
  result_revision: number;
  state: "ready" | "incomplete" | "unavailable";
  selected_scenario_id: string | null;
  coordinate_system: "x=width,y=height,z=depth; origin=front-left-bottom";
  objects: SceneObject[];
  warnings: string[];
  assumptions: string[];
  collision_status: "not_evaluated";
}

/** SceneObject */
export interface SceneObject {
  id: string;
  piece_id: string;
  proposal_id: string;
  role: string;
  label: string;
  occurrence_index: number;
  position_mm: Point3D;
  dimensions_mm: Size3D;
  bbox_mm: Bounds3D;
  source_contour_ids: string[];
  evidence_ids: string[];
  placement_basis: string;
  part_observation_id: string | null;
  placement_status: "hypothesis" | "human_selected";
  placement_constraint_ids: string[];
}

/** Size3D */
export interface Size3D {
  x: number;
  y: number;
  z: number;
}

/** ClarificationAnswer */
export interface ClarificationAnswer {
  question: string;
  answer: string;
}

/** EnvelopeConstraints */
export interface EnvelopeConstraints {
  width?: number | null;
  depth?: number | null;
  height?: number | null;
}

/** GeneralAutoReviewRequest */
export interface GeneralAutoReviewRequest {
  base_proposal_revision: number;
  base_review_revision: number;
}

/** GeneralFurnitureReviewRequest */
export interface GeneralFurnitureReviewRequest {
  base_proposal_revision: number;
  base_review_revision: number;
  reviewer_name: string;
  reason: string;
  operations: GeneralReviewOperation[];
  components: GeneralComponentReview[];
  furniture_quantity?: GeneralQuantity;
  currency?: string | null;
  required_cost_scope?: string[];
  required_hours_scope?: string[];
}

/** GeneralProposalRequest */
export interface GeneralProposalRequest {
  mode: "live" | "manual";
  base_proposal_revision: number;
  proposal?: GeneralFurnitureProposal | null;
}

/** ReconstructionRequest */
export interface ReconstructionRequest {
  intended_use?: string;
}

/** RefinementRequest */
export interface RefinementRequest {
  answers?: ClarificationAnswer[];
  intended_use?: string | null;
  envelope_mm?: EnvelopeConstraints;
}

/** RunRequest */
export interface RunRequest {
  document_id: string;
  mode: "live" | "geometry_only" | "recorded_replay";
  input_kind?: "mounted_views_legacy" | "separated_part_views" | "mounted_orthographic_views" | "general_furniture";
  table_profile?: "rectangular_table_v1" | null;
  proposal_mode?: "none" | "catalog_baseline" | "model_generated";
  table_template_id?: "side_supports_v1" | "corner_supports_v1" | null;
}
