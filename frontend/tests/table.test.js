import test from "node:test";
import assert from "node:assert/strict";
import * as table from "../core/table.js";

import { artifactRequestIdentity, buildTableCostScope, buildTableReviewPayload, componentMaterialOverrides, normaliseTableCostCatalog, normaliseTableDrawingManifest, normaliseTableWorkspace, presentTableComponentExplanation, presentTableCosts, tableExportFormat, tableMaterialScopeSelection, tableRunOptions } from "../core/table.js";

test("row selection opens only the drawing of that component, never the first unrelated sheet", () => {
  assert.equal(typeof table.componentDrawingSheet, "function");
  const top = { id: "sheet-top", componentId: "top" };
  const side = { id: "sheet-side", componentId: "side" };
  const manifest = { byKind: { components: [top, side] } };
  assert.equal(table.componentDrawingSheet(manifest, "side"), side);
  assert.equal(table.componentDrawingSheet(manifest, "top"), top);
  assert.equal(table.componentDrawingSheet(manifest, "absent"), null);
  assert.equal(table.componentDrawingSheet(null, "top"), null);
});

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
    proposal_mode: "model_generated",
  });
});

test("table CSV export requests the revision-bound cut list format", () => {
  assert.equal(tableExportFormat("csv"), "table_cutlist");
  assert.equal(tableExportFormat("json"), "json");
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

test("drawing manifest accepts a same origin deployment prefix but rejects external artifact URLs", () => {
  const manifest = normaliseTableDrawingManifest({ result_revision: 1, program_hash: "a".repeat(64), sheets: [{ sheet_id: "general", kind: "general", result_revision: 1, program_hash: "a".repeat(64), formats: [{ format: "svg", url: "/vexplorer/api/v1/runs/run/table-drawings/general.svg" }, { format: "dxf", url: "https://external.invalid/file.dxf" }] }] });
  assert.equal(manifest.sheets[0].formatLinks.svg, "/vexplorer/api/v1/runs/run/table-drawings/general.svg");
  assert.equal(manifest.sheets[0].formatLinks.dxf, undefined);
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
  assert.equal(workspace.measures[2].effectiveState, "calculated");
  assert.equal(workspace.measures[2].effectivePrefix, "Propuesta");
  assert.equal(workspace.measures[2].effectiveLabel, "Calculado");
  assert.equal(workspace.measures[2].humanEffective, false);
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

test("a prior human table value stays editable and supersedes its confirmation", () => {
  const snapshot = { result_revision: 4, result: {
    input_semantics: "mounted_orthographic_views",
    table_analysis: { warnings: [], measures: [{ id: "m-slot", semantic: "tabletop_thickness", value_mm: null, state: "unknown", slot_origin: "profile_required_slot" }] },
    table_programs: [{ id: "program-side", proposal_origin: "catalog_baseline", assumptions: [], premises: [], components: [] }],
    table_confirmed_values: [{ confirmation_id: "confirmation-old", target_id: "m-slot", value_mm: 18, reason: "Medición anterior", source: "human" }],
  } };
  const workspace = normaliseTableWorkspace(snapshot);
  assert.equal(workspace.measures[0].confirmable, true);
  assert.equal(workspace.measures[0].effectiveValue, 18);
  assert.equal(workspace.measures[0].effectiveState, "confirmed");
  assert.equal(workspace.measures[0].effectivePrefix, "Vigente");
  assert.equal(workspace.measures[0].effectiveLabel, "Confirmado por persona");
  assert.equal(workspace.measures[0].humanEffective, true);
  assert.equal(workspace.measures[0].confirmation.reason, "Medición anterior");

  const payload = buildTableReviewPayload(snapshot, workspace, {
    reviewerName: "Servidor",
    programId: "program-side",
    notes: "Se corrige la comprobación previa.",
    confirmedValues: [{ targetId: "m-slot", valueMm: "19", reason: "Nueva medición", confirmationId: "confirmation-new" }],
  });
  assert.deepEqual(payload.table_confirmed_values, [{ confirmation_id: "confirmation-new", supersedes_confirmation_id: "confirmation-old", target_kind: "measurement_slot", target_id: "m-slot", value_mm: 19, reason: "Nueva medición", source: "human" }]);
});

test("observed corrections and recovered source decisions preserve evidence and intent", () => {
  const snapshot = { result_revision: 2, result: {
    input_semantics: "mounted_orthographic_views",
    table_analysis: { warnings: ["recovered_dxf:fixes=1:errors=0"], measures: [{ id: "m-width", semantic: "overall_width", value_mm: 1200, state: "observed", evidence_ids: ["evidence-1"], slot_origin: "drawing" }] },
    table_programs: [{ id: "program-side", proposal_origin: "catalog_baseline", assumptions: [], premises: [], components: [] }],
    evaluated_table_program: { raw_program: { id: "program-side" }, state: "needs_review", bindings: [], components: [], issues: [{ code: "source_recovery_review_required", severity: "review", message: "Revisión de fuente requerida", target_ids: ["source-warning-1", "recovered_dxf:fixes=1:errors=0"] }] },
  } };
  const workspace = normaliseTableWorkspace(snapshot);
  assert.equal(workspace.measures[0].correctable, true);
  assert.equal(workspace.sourceWarnings[0].id, "source-warning-1");
  const payload = buildTableReviewPayload(snapshot, workspace, {
    reviewerName: "Servidor", programId: "program-side", notes: "Se revisa contra el original.",
    observedCorrections: [{ targetId: "m-width", valueMm: 1200.05, reason: "Comprobado", correctionId: "correction-1" }],
    sourceDecisions: [{ warningId: "source-warning-1", warningCode: "recovered_dxf:fixes=1:errors=0", action: "accept", reason: "Comparado con el DXF original" }],
  });
  assert.deepEqual(payload.table_observed_value_corrections, [{ correction_id: "correction-1", measurement_id: "m-width", value_mm: 1200.05, reason: "Comprobado", evidence_ids: ["evidence-1"], source: "human" }]);
  assert.deepEqual(payload.table_source_review_decisions, [{ warning_id: "source-warning-1", warning_code: "recovered_dxf:fixes=1:errors=0", action: "accept", reason: "Comparado con el DXF original" }]);
});

test("copy bindings never turn an observed source measure into a human confirmation", () => {
  const workspace = normaliseTableWorkspace({ result_revision: 1, result: {
    input_semantics: "mounted_orthographic_views",
    table_analysis: { measures: [{ id: "m-width", semantic: "overall_width", value_mm: 1200, state: "observed", evidence_ids: ["e-1"] }] },
    table_programs: [{ id: "program", proposal_origin: "catalog_baseline", assumptions: [], premises: [], components: [] }],
    evaluated_table_program: { raw_program: { id: "program" }, state: "hypothesis", components: [], issues: [], bindings: [{ operation: "copy", operand_refs: [{ ref_type: "measure", ref_id: "m-width" }], result: { value_mm: 1200, state: "calculated" } }] },
  } });
  const measure = workspace.measures[0];
  assert.equal(measure.state, "observed");
  assert.equal(measure.effectiveValue, 1200);
  assert.equal(measure.effectiveState, "calculated");
  assert.equal(measure.effectivePrefix, "Propuesta");
  assert.equal(measure.effectiveLabel, "Calculado");
  assert.equal(measure.humanEffective, false);
});

test("accepted and rejected source decisions remain visible and rectifiable", () => {
  const warningCode = "recovered_dxf:fixes=1:errors=0";
  const base = {
    input_semantics: "mounted_orthographic_views",
    table_analysis: { ledger_revision: "ledger-1", warnings: [warningCode], measures: [] },
    table_programs: [{ id: "program", proposal_origin: "catalog_baseline", assumptions: [], premises: [], components: [] }],
    table_source_review_decisions: [{ warning_id: "source-warning-1", warning_code: warningCode, action: "accept", reason: "Fuente cotejada" }],
    evaluated_table_program: { raw_program: { id: "program" }, state: "needs_review", bindings: [], components: [], issues: [] },
  };
  const accepted = normaliseTableWorkspace({ result_revision: 2, result: base });
  assert.deepEqual(accepted.sourceWarnings[0], { id: "source-warning-1", code: warningCode, message: warningCode, currentAction: "accept", currentReason: "Fuente cotejada" });

  const rejected = normaliseTableWorkspace({ result_revision: 3, result: { ...base,
    table_source_review_decisions: [{ warning_id: "source-warning-1", warning_code: warningCode, action: "reject", reason: "Fuente ilegible" }],
    evaluated_table_program: { ...base.evaluated_table_program, issues: [{ code: "source_recovery_rejected", severity: "error", message: "Fuente rechazada", target_ids: ["source-warning-1", warningCode] }] },
  } });
  assert.equal(rejected.sourceWarnings.length, 1);
  assert.equal(rejected.sourceWarnings[0].currentAction, "reject");
  assert.equal(rejected.sourceWarnings[0].currentReason, "Fuente ilegible");
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

test("real catalog provenance, hours and provisional sale price remain server authoritative", () => {
  const catalog = normaliseTableCostCatalog({
    catalog_version: "taller-2026-11", source: "Tarifas aprobadas por Compras", effective_date: "2026-11-01", synthetic: false,
    tariffs: [
      { id: "labor-1", label: "Montaje", concept_type: "labor", scope: "labor", rate_eur_per_unit: 31.5, rate_unit: "EUR/h", synthetic: false },
      { id: "finish-1", label: "Barniz", concept_type: "finish", scope: "finishing", rate_eur_per_unit: 12, rate_unit: "EUR/m2", synthetic: false },
    ],
  });
  assert.equal(catalog.synthetic, false);
  assert.equal(catalog.source, "Tarifas aprobadas por Compras");
  assert.equal(catalog.effectiveDate, "2026-11-01");
  assert.equal(catalog.labor[0].id, "labor-1");
  assert.equal(catalog.finishing[0].id, "finish-1");

  const result = presentTableCosts({
    result_revision: 5, catalog_version: "taller-2026-11", synthetic: false, catalog_snapshot: { source: "Tarifas aprobadas por Compras", effective_date: "2026-11-01" },
    known_subtotal_eur: 210, grand_total_eur: 210, total_state: "complete", total_hours: 4.5,
    principal_cost_contributor_id: "labor", provisional_margin_percent: 30, provisional_sale_price_eur: 300,
    concepts: [
      { id: "labor", label: "Montaje", quantity: 4.5, quantity_unit: "h", rate_eur_per_unit: 31.5, rate_unit: "EUR/h", amount_eur: 141.75, state: "resolved" },
      { id: "edge", label: "Canteado", quantity: null, quantity_unit: "m", rate_eur_per_unit: null, rate_unit: "EUR/m", amount_eur: null, state: "not_applicable" },
    ],
  });
  assert.equal(result.hoursLabel, "4,5 h");
  assert.equal(result.salePriceLabel, "300,00 €");
  assert.equal(result.marginLabel, "30 %");
  assert.equal(result.largestContribution.id, "labor");
  assert.equal(result.items[1].stateLabel, "No aplica");
  assert.match(result.catalogLabel, /Tarifas aprobadas/);
});

test("complete economic scope sends selected hours, finish, exclusions and explicit margin", () => {
  assert.deepEqual(buildTableCostScope({
    materialTariffId: "material-1", edgeScope: "all_exposed", edgeTariffId: "edge-1",
    operations: [{ id: "cut-1", hours: "1.5" }, { id: "drill-1", hours: "" }],
    laborTariffId: "labor-1", laborHours: "3", finishTariffId: "finish-1", finishQuantity: "2.25",
    exclusions: [], marginPercent: "30",
  }), {
    material_tariff_id: "material-1", component_material_tariff_ids: {}, edge_scope: "all_exposed", edge_tariff_id: "edge-1",
    operation_tariff_ids: ["cut-1", "drill-1"], operation_hours_by_tariff: { "cut-1": 1.5 },
    labor_tariff_id: "labor-1", labor_hours: 3, finish_tariff_id: "finish-1", finish_quantity_m2: 2.25,
    exclusions: [], provisional_margin_percent: 30,
  });
  assert.deepEqual(buildTableCostScope({ exclusions: [{ scope: "operation", reason: "Taladrado realizado por proveedor" }] }).exclusions, [{ scope: "operation", reason: "Taladrado realizado por proveedor" }]);
  assert.throws(() => buildTableCostScope({ exclusions: [{ scope: "labor", reason: " " }] }), /motivo/i);
  assert.throws(() => buildTableCostScope({ operations: [{ id: "cut-1", hours: "1" }], exclusions: [{ scope: "operation", reason: "No aplica" }] }), /operaciones.*excluidas/i);
  assert.throws(() => buildTableCostScope({ edgeScope: "all_exposed", edgeTariffId: "edge-1", exclusions: [{ scope: "edge", reason: "No aplica" }] }), /canteado.*excluido/i);
});

test("component material overrides use current component ids and discard stale controls", () => {
  const components = [{ id: "top", role: "tabletop" }, { id: "left-support", role: "side_support" }];
  assert.deepEqual(componentMaterialOverrides(components, {
    top: "oak-board", "left-support": "birch-board", "removed-leg": "old-board", empty: "", unknown: "unknown-board",
  }, [{ id: "oak-board" }, { id: "birch-board" }]), { top: "oak-board", "left-support": "birch-board" });
  assert.deepEqual(componentMaterialOverrides([{ id: "new-leg", role: "corner_support" }], {
    top: "oak-board", "left-support": "birch-board",
  }, [{ id: "oak-board" }, { id: "birch-board" }]), {});
});

test("saved material scope round trips and reports missing catalog or component references", () => {
  const components = [{ id: "top" }, { id: "support" }], materials = [{ id: "general-board" }, { id: "oak-board" }];
  assert.deepEqual(tableMaterialScopeSelection({ material_tariff_id: "general-board", component_material_tariff_ids: { top: "oak-board" } }, components, materials), {
    materialTariffId: "general-board", componentMaterialTariffIds: { top: "oak-board" }, warnings: [],
  });
  const stale = tableMaterialScopeSelection({ material_tariff_id: "retired", component_material_tariff_ids: { top: "missing", removed: "oak-board" } }, components, materials);
  assert.equal(stale.materialTariffId, "");
  assert.deepEqual(stale.componentMaterialTariffIds, {});
  assert.equal(stale.warnings.length, 3);
});

test("table explanation presents backend formulas, premises and unknowns without recomputing them", () => {
  const explanation = presentTableComponentExplanation({ pieces: [{ piece_id: "top", formulas: [{ field: "length_mm", expression: "length_mm=binding:top_length", operands_mm: { "measure:m-width": 1200 }, result_mm: 1200 }], premises: ["Tapa rectangular"], unknown_fields: ["thickness_mm"], field_states: { length_mm: "calculated", thickness_mm: "unknown" } }], warnings: ["Confirma el espesor"] }, "top");
  assert.deepEqual(explanation.formulas, [{ fieldLabel: "Largo", expression: "length_mm=binding:top_length", operandsLabel: "measure:m-width = 1200 mm", resultLabel: "1200 mm" }]);
  assert.deepEqual(explanation.premises, ["Tapa rectangular"]);
  assert.deepEqual(explanation.unknownLabels, ["Grosor"]);
  assert.deepEqual(explanation.warnings, ["Confirma el espesor"]);
});
