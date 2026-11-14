import test from "node:test";
import assert from "node:assert/strict";

import { artifactRequestIdentity, buildTableReviewPayload, normaliseTableCostCatalog, normaliseTableDrawingManifest, normaliseTableWorkspace, presentTableComponentExplanation, presentTableCosts, tableRunOptions } from "../core/table.js";

test("table run options keep catalog baseline and live model generation visibly distinct", () => {
  assert.deepEqual(tableRunOptions("geometry_only", "side_supports_v1"), {
    table_profile: "rectangular_table_v1",
    proposal_mode: "catalog_baseline",
    table_template_id: "side_supports_v1",
  });
  assert.deepEqual(tableRunOptions("live"), {
    table_profile: "rectangular_table_v1",
    proposal_mode: "model_generated",
  });
  assert.deepEqual(tableRunOptions("recorded_replay"), {
    table_profile: "rectangular_table_v1",
    proposal_mode: "none",
  });
});

test("drawing manifest preserves revision, hash, incomplete warnings and selectable formats", () => {
  const manifest = normaliseTableDrawingManifest({
    result_revision: 3,
    program_hash: "program-3",
    sheets: [
      { sheet_id: "general", kind: "general", title: "Plano general", page: 1, result_revision: 3, program_hash: "program-3", status: "ready", warnings: [], formats: ["svg", "dxf"] },
      { sheet_id: "top", kind: "component", title: "Tapa", component_id: "component-top", page: 2, result_revision: 3, program_hash: "program-3", status: "incomplete", warnings: ["Espesor desconocido"], formats: [{ format: "svg", media_type: "image/svg+xml", url: "/api/v1/runs/run/table-drawings/top.svg" }] },
    ],
  });

  assert.equal(manifest.revision, 3);
  assert.equal(manifest.programHash, "program-3");
  assert.deepEqual(manifest.byKind.general.map((sheet) => sheet.id), ["general"]);
  assert.deepEqual(manifest.byKind.components.map((sheet) => sheet.id), ["top"]);
  assert.deepEqual(manifest.byKind.cut_sheet, []);
  assert.deepEqual(manifest.sheets[1], {
    id: "top",
    kind: "component",
    title: "Tapa",
    componentId: "component-top",
    page: 2,
    revision: 3,
    programHash: "program-3",
    status: "incomplete",
    warnings: ["Espesor desconocido"],
    formats: ["svg"],
    formatLinks: { svg: "/api/v1/runs/run/table-drawings/top.svg" },
  });
});

test("artifact identity fences fast sheet changes across runs and revisions", () => {
  assert.equal(artifactRequestIdentity({ runId: "run-a", revision: 3, programHash: "hash-a", sheetId: "top", format: "svg" }), "run-a:3:hash-a:top:svg");
  assert.notEqual(
    artifactRequestIdentity({ runId: "run-a", revision: 3, programHash: "hash-a", sheetId: "top", format: "svg" }),
    artifactRequestIdentity({ runId: "run-a", revision: 4, programHash: "hash-b", sheetId: "top", format: "svg" }),
  );
});

test("table workspace keeps source measures separate from generated and evaluated components", () => {
  const workspace = normaliseTableWorkspace({
    result_revision: 1,
    result: {
      input_semantics: "mounted_orthographic_views",
      selected_table_program_id: null,
      table_analysis: {
        ledger_revision: "ledger-1",
        state: "needs_review",
        warnings: ["Falta espesor"],
        measures: [
          { id: "m-width", semantic: "overall_width", axis: "width", value_mm: 1200, state: "observed", measurement_ids: ["dim-1"], view_ids: ["front"], evidence_ids: ["ev-1"], source_entity_ids: ["entity-1"], slot_origin: "drawing", geometry_relation: "dimension_annotation" },
          { id: "m-support", semantic: "support_width", axis: "section", value_mm: 30, state: "observed", measurement_ids: [], view_ids: ["front"], evidence_ids: ["ev-2"], source_entity_ids: ["line-1"], slot_origin: "drawing", geometry_relation: "opposite_offsets" },
          { id: "m-thickness", semantic: "tabletop_thickness", axis: "section", value_mm: null, state: "unknown", measurement_ids: [], view_ids: [], evidence_ids: [], source_entity_ids: [], slot_origin: "profile_required_slot", geometry_relation: "profile_required_slot" },
        ],
      },
      table_programs: [{
        id: "program-side",
        proposal_origin: "catalog_baseline",
        table_template_id: "side_supports_v1",
        assumptions: ["La tapa apoya sobre los laterales"],
        premises: [{ id: "premise-topology", kind: "topology", required: true, description: "Tapa y dos soportes" }],
        components: [
          { id: "top", role: "tabletop", quantity_rule_id: "top_one", premise_ids: ["premise-topology"], evidence_ids: ["ev-1"] },
          { id: "sides", role: "side_support", quantity_rule_id: "two_side_supports", premise_ids: ["premise-topology"], evidence_ids: [] },
        ],
      }],
      evaluated_table_program: {
        raw_program: { id: "program-side" },
        program_hash: "a".repeat(64),
        state: "needs_review",
        bindings: [{ id: "binding-thickness", operation: "copy", operand_refs: [{ ref_type: "measure", ref_id: "m-thickness" }], result: { value_mm: 18, state: "calculated", dependency_refs: ["measure:m-thickness"], evidence_ids: [] } }],
        components: [{ id: "top", role: "tabletop", length: { value_mm: 1200, state: "calculated", dependency_refs: ["measure:m-width"], evidence_ids: ["ev-1"] }, width: { value_mm: 700, state: "calculated" }, thickness: { value_mm: null, state: "unknown" }, quantity: 1, accepted: false }],
        issues: [{ code: "unknown_thickness", severity: "review", message: "Confirma el espesor", target_ids: ["m-thickness"] }],
      },
    },
  });

  assert.equal(workspace.isTable, true);
  assert.equal(workspace.measures[0].informationClass, "observed");
  assert.equal(workspace.measures[0].sourceLabel, "Cota escrita");
  assert.equal(workspace.measures[1].sourceLabel, "Medición CAD · separaciones opuestas");
  assert.equal(workspace.measures[2].informationClass, "unknown");
  assert.equal(workspace.measures[2].confirmable, true);
  assert.equal(workspace.measures[2].effectiveValue, 18);
  assert.equal(workspace.programs[0].originLabel, "Baseline de catálogo");
  assert.equal(workspace.programs[0].components[1].quantity, 2);
  assert.equal(workspace.evaluated.components[0].thickness.state, "unknown");
  assert.deepEqual(workspace.evaluated.components[0].length.dependencyRefs, ["measure:m-width"]);
});

test("non blocking profile slots stay in the ledger without asking the reviewer for values", () => {
  const workspace = normaliseTableWorkspace({
    result_revision: 1,
    result: {
      input_semantics: "mounted_orthographic_views",
      table_analysis: { measures: [
        { id: "m-unused", semantic: "support_width", value_mm: null, state: "unknown", slot_origin: "profile_required_slot" },
        { id: "m-required", semantic: "support_depth", value_mm: null, state: "unknown", slot_origin: "profile_required_slot" },
      ] },
      table_programs: [],
      evaluated_table_program: {
        state: "hypothesis",
        bindings: [],
        components: [],
        measurement_dispositions: [
          { measurement_id: "m-unused", reason: "No lo usa esta topología", blocking: false },
          { measurement_id: "m-required", reason: "Necesario para colocar el soporte", blocking: true },
        ],
      },
    },
  });

  assert.equal(workspace.measures.find((item) => item.id === "m-unused").confirmable, false);
  assert.equal(workspace.measures.find((item) => item.id === "m-unused").dispositionReason, "No lo usa esta topología");
  assert.equal(workspace.measures.find((item) => item.id === "m-required").confirmable, true);
});

test("table review accepts explicit targets and only confirms declared unresolved measurement slots", () => {
  const workspace = normaliseTableWorkspace({
    result_revision: 1,
    result: {
      input_semantics: "mounted_orthographic_views",
      table_analysis: { measures: [
        { id: "m-observed", semantic: "overall_width", value_mm: 1200, state: "observed", slot_origin: "drawing" },
        { id: "m-slot", semantic: "tabletop_thickness", value_mm: null, state: "unknown", slot_origin: "profile_required_slot" },
      ] },
      table_programs: [{ id: "program-side", proposal_origin: "catalog_baseline", assumptions: [], premises: [], bindings: [], components: [{ id: "top", role: "tabletop", premise_ids: [], evidence_ids: [] }] }],
    },
  });
  const payload = buildTableReviewPayload({ result_revision: 1 }, workspace, {
    reviewerName: "Ana Técnica",
    programId: "program-side",
    notes: "Se confirma el sistema y el espesor medido en taller.",
    decisions: [
      { targetKind: "program", targetId: "program-side", action: "accept", reason: "Sistema validado" },
      { targetKind: "component", targetId: "top", action: "accept", reason: "Componente validado" },
    ],
    confirmedValues: [
      { targetId: "m-slot", valueMm: "18", reason: "Medición de taller" },
      { targetId: "m-observed", valueMm: "1300", reason: "No debe sobrescribirse" },
    ],
  });

  assert.deepEqual(payload, {
    base_result_revision: 1,
    reviewer_name: "Ana Técnica",
    table_program_id: "program-side",
    table_decisions: [
      { target_kind: "program", target_id: "program-side", action: "accept", reason: "Sistema validado" },
      { target_kind: "component", target_id: "top", action: "accept", reason: "Componente validado" },
    ],
    table_confirmed_values: [{ target_kind: "measurement_slot", target_id: "m-slot", value_mm: 18, reason: "Medición de taller", source: "human" }],
    notes: "Se confirma el sistema y el espesor medido en taller.",
  });
});

test("table costs expose explicit tariffs, partial subtotal and largest known contribution", () => {
  const catalog = normaliseTableCostCatalog({ catalog_version: "synthetic-1", synthetic: true, tariffs: [{ id: "board-1", label: "Tablero demo", scope: "material", rate_eur_per_unit: 42, rate_unit: "EUR/m2" }, { id: "edge-1", label: "Canteado expuesto", scope: "edge", rate_eur_per_unit: 1.5, rate_unit: "EUR/m" }, { id: "cut-1", label: "Corte", scope: "operation", rate_eur_per_unit: 3, rate_unit: "EUR/unit" }] });
  assert.deepEqual(catalog.materials[0], { id: "board-1", label: "Tablero demo", rate: 42, rateUnit: "EUR/m2" });
  assert.equal(catalog.edges[0].rate, 1.5);
  const result = presentTableCosts({
    result_revision: 2,
    program_hash: "b".repeat(64),
    catalog_version: "synthetic-1",
    known_subtotal_eur: 104,
    grand_total_eur: null,
    total_state: "partial",
    warnings: ["Acabado sin tarifa"],
    concepts: [
      { id: "fixed", label: "Preparación", concept_type: "fixed", component_id: null, occurrence_ids: [], formula: "1 × 20", quantity: 1, quantity_unit: "unit", rate_eur_per_unit: 20, rate_unit: "EUR/unit", amount_eur: 20, state: "resolved", required: true, dependency_refs: [] },
      { id: "material-top", label: "Material de tapa", concept_type: "material_area", component_id: "top", occurrence_ids: ["top-1"], formula: "2 m² × 42 EUR/m²", quantity: 2, quantity_unit: "m2", rate_eur_per_unit: 42, rate_unit: "EUR/m2", amount_eur: 84, state: "resolved", required: true, dependency_refs: ["component:top"] },
      { id: "finish", label: "Acabado", concept_type: "finish", component_id: "top", occurrence_ids: ["top-1"], formula: "tarifa pendiente", quantity: null, quantity_unit: "m2", rate_eur_per_unit: null, rate_unit: "EUR/m2", amount_eur: null, state: "unknown", required: true, dependency_refs: ["component:top"] },
    ],
  });
  assert.equal(result.complete, false);
  assert.match(result.totalLabel, /Subtotal conocido/);
  assert.equal(result.largestContribution.id, "material-top");
  assert.equal(result.items[2].amountLabel, "Pendiente");
});

test("table explanation presents backend formulas, premises and unknowns without recomputing them", () => {
  const explanation = presentTableComponentExplanation({ pieces: [{ piece_id: "top", formulas: [{ field: "length_mm", expression: "length_mm=binding:top_length", operands_mm: { "measure:m-width": 1200 }, result_mm: 1200 }], premises: ["Tapa rectangular"], unknown_fields: ["thickness_mm"], field_states: { length_mm: "calculated", thickness_mm: "unknown" } }], warnings: ["Confirma el espesor"] }, "top");
  assert.deepEqual(explanation.formulas, [{ fieldLabel: "Largo", expression: "length_mm=binding:top_length", operandsLabel: "measure:m-width = 1200 mm", resultLabel: "1200 mm" }]);
  assert.deepEqual(explanation.premises, ["Tapa rectangular"]);
  assert.deepEqual(explanation.unknownLabels, ["Grosor"]);
  assert.deepEqual(explanation.warnings, ["Confirma el espesor"]);
});
