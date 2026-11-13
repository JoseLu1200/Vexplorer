import test from "node:test";
import assert from "node:assert/strict";

import { normalisePartsWorkspace, partSelectionViewIds, presentDescriptorV2 } from "../core/parts.js";
import { buildAssemblyReviewPayload } from "../core/review.js";

const snapshot = {
  result_revision: 1,
  agent_selected_scenario_id: "assembly-between",
  result: {
    input_semantics: "separated_part_views",
    part_analysis: {
      schema_version: "0.4.0",
      candidate_revision: "parts-r1",
      observations: [{
        id: "part-obs-A", part_key: "A", association_basis: "explicit_key", status: "partial",
        views: [
          { view_id: "view-A-front", role: "FRONT" },
          { view_id: "view-A-top", role: "TOP" },
          { view_id: "view-A-side", role: "SIDE" },
        ],
        dimensions: {
          length: { value_mm: 900, state: "observed", evidence_ids: ["ev-l"], measurement_ids: ["dim-l"], view_ids: ["view-A-front"] },
          width: { value_mm: 300, state: "observed", evidence_ids: ["ev-w"], measurement_ids: ["dim-w"], view_ids: ["view-A-front"] },
          thickness: { value_mm: null, state: "unknown", evidence_ids: [], measurement_ids: [], view_ids: [] },
        },
        quantity: { value: null, state: "unknown", evidence_ids: [] },
        source_entity_ids: ["entity-a"], evidence_ids: ["ev-a"], warnings: ["missing_thickness"],
      }],
    },
    assembly_candidates: [{
      id: "assembly-between", family: "rectangular_shelving", family_status: "hypothesis",
      layout: "between_sides", layout_status: "hypothesis", state: "hypothesis", needs_review: true,
      uses: [{ id: "use-shelves", part_observation_id: "part-obs-A", role: "shelf", role_status: "hypothesis", source_quantity: null, allocated_quantity: null, occurrence_indices: [], quantity_source: "unknown", evidence_ids: ["ev-a"] }],
      unassigned_part_observation_ids: [], constraints: [], derived_dimensions: [], unknown_fields: ["quantity", "thickness"],
      assumptions: ["Role allocation is a dimensional hypothesis; opaque part keys carry no role semantics."], evidence_ids: ["ev-a"],
    }],
  },
};

test("three associated views stay one observation and never become quantity", () => {
  const workspace = normalisePartsWorkspace(snapshot);
  assert.equal(workspace.isPartsOnly, true);
  assert.equal(workspace.observations.length, 1);
  assert.deepEqual(workspace.observations[0].viewIds, ["view-A-front", "view-A-top", "view-A-side"]);
  assert.deepEqual(workspace.observations[0].quantity, { value: null, state: "unknown", evidenceIds: [] });
  assert.equal(workspace.observations[0].label, "Pieza A");
});

test("part selection exposes only its explicitly associated views", () => {
  const workspace = normalisePartsWorkspace(snapshot);
  assert.deepEqual([...partSelectionViewIds(workspace, "part-obs-A")], ["view-A-front", "view-A-top", "view-A-side"]);
  assert.equal(partSelectionViewIds(workspace, "all"), null);
});

test("assembly candidates remain hypotheses with unknowns and premises visible", () => {
  const workspace = normalisePartsWorkspace(snapshot);
  const candidate = workspace.candidates[0];
  assert.equal(workspace.suggestedCandidateId, "assembly-between");
  assert.equal(candidate.familyState, "hypothesis");
  assert.equal(candidate.layoutState, "hypothesis");
  assert.deepEqual(candidate.unknownFields, ["quantity", "thickness"]);
  assert.deepEqual(candidate.assumptions, ["La asignación de roles es una hipótesis dimensional; las claves de pieza no indican su función."]);
  assert.equal(candidate.assignmentLabel, "Pieza A → Balda");
  assert.equal(candidate.uses[0].id, "use-shelves");
  assert.deepEqual(candidate.uses[0].sourceQuantity, { value: null, state: "unknown", evidenceIds: ["ev-a"] });
  assert.deepEqual(candidate.uses[0].allocatedQuantity, { value: null, state: "unknown", evidenceIds: ["ev-a"] });
  assert.deepEqual(candidate.uses[0].occurrenceIndices, []);
});

test("assembly review decisions address use ids and preserve only human supplied values", () => {
  assert.deepEqual(buildAssemblyReviewPayload(snapshot, {
    assembly_candidate_id: "assembly-between", reviewer_name: "Ana", notes: "Cantidad confirmada en taller.",
    decisions: [{ use_id: "use-shelves", role: "shelf", quantity: 2, length_mm: 900, width_mm: 300, thickness_mm: 18, notes: "Dos ocurrencias" }],
  }), {
    base_result_revision: 1, reviewer_name: "Ana", assembly_candidate_id: "assembly-between", notes: "Cantidad confirmada en taller.",
    decisions: [{ proposal_id: "use-shelves", action: "confirm", role: "shelf", quantity: 2, length_mm: 900, width_mm: 300, thickness_mm: 18, material: null, finish: null, notes: "Dos ocurrencias" }],
  });
});

test("assembly review selects a candidate without inventing thickness or quantities", () => {
  assert.deepEqual(buildAssemblyReviewPayload(snapshot, {
    assembly_candidate_id: "assembly-between", reviewer_name: "Ana", notes: "Confirmo la premisa de montaje.",
  }), {
    base_result_revision: 1,
    reviewer_name: "Ana",
    assembly_candidate_id: "assembly-between",
    notes: "Confirmo la premisa de montaje.",
  });
});

test("descriptor v2 presents thicknesses and classification state explicitly", () => {
  assert.deepEqual(presentDescriptorV2({
    descriptor_version: "furniture-v2", family: "rectangular_shelving", structure: "top_base_between_sides",
    thicknesses_mm: [18, 19], classification_status: "hypothesis", unknown_fields: ["material"],
  }), {
    version: "furniture-v2", familyLabel: "Estantería rectangular", structureLabel: "Tapa y base entre laterales",
    thicknessLabel: "18 mm · 19 mm", classificationLabel: "Hipótesis", unknownLabels: ["Material"],
  });
});
