import test from "node:test";
import assert from "node:assert/strict";
import {
  collectCoincidences,
  explainSimilarityMatch,
  formatDifference,
  formatScoreBreakdown,
} from "../core/similarity_explain.js";

test("formatDifference formats dimension changes with signed deltas and handles None/null", () => {
  const wider = formatDifference({
    field: "dimensions.width_mm",
    query_value: "900.0",
    candidate_value: "950.0",
  });
  assert.equal(wider.summary, "Ancho: 900 mm -> 950 mm (+50 mm)");
  assert.equal(wider.technical, "dimensions.width_mm: 900.0 -> 950.0");

  const shallower = formatDifference({
    field: "dimensions.depth_mm",
    query_value: "450",
    candidate_value: "400",
  });
  assert.equal(shallower.summary, "Fondo: 450 mm -> 400 mm (-50 mm)");

  const unknownHeight = formatDifference({
    field: "dimensions.height_mm",
    query_value: "None",
    candidate_value: "2100",
  });
  assert.equal(unknownHeight.summary, "Alto: Desconocido -> 2100 mm");

  const nullDepth = formatDifference({
    field: "dimensions.depth_mm",
    query_value: 400,
    candidate_value: null,
  });
  assert.equal(nullDepth.summary, "Fondo: 400 mm -> Desconocido");
});

test("formatDifference formats roles, thicknesses, structure, material, finish and hides component reprs", () => {
  assert.equal(
    formatDifference({ field: "roles.shelf", query_value: "2", candidate_value: "3" }).summary,
    "Baldas: 2 -> 3 (+1)",
  );
  assert.equal(
    formatDifference({ field: "roles.side", query_value: "2", candidate_value: "None" }).summary,
    "Costados: 2 -> Desconocido",
  );
  assert.equal(
    formatDifference({ field: "thicknesses_mm", query_value: "[18.0]", candidate_value: "[22.0]" }).summary,
    "Espesor: 18 mm -> 22 mm (+4 mm)",
  );
  assert.equal(
    formatDifference({ field: "thicknesses_mm", query_value: "[18.0]", candidate_value: "[18.0, 22.0]" }).summary,
    "Espesor: 18 mm -> 18, 22 mm",
  );
  assert.equal(
    formatDifference({
      field: "structure",
      query_value: "top_base_between_sides",
      candidate_value: "top_base_cap_sides",
    }).summary,
    "Estructura: entre costados -> sobre costados",
  );
  assert.equal(
    formatDifference({ field: "material", query_value: "None", candidate_value: "Roble" }).summary,
    "Material: Desconocido -> Roble",
  );
  assert.equal(
    formatDifference({ field: "finish", query_value: "Mate", candidate_value: "Satinado" }).summary,
    "Acabado: Mate -> Satinado",
  );

  const repr = "TableDescriptorComponentFeature(role='tabletop', quantity=1)";
  const comp = formatDifference({ field: "components", query_value: repr, candidate_value: repr });
  assert.equal(comp.summary, "Componentes: configuración distinta");
  assert.equal(comp.summary.includes("TableDescriptorComponentFeature"), false);
  assert.match(comp.technical, /TableDescriptorComponentFeature/);
});

test("formatScoreBreakdown formats geometric and semantic score_components without calling them probabilities", () => {
  const geometric = formatScoreBreakdown({
    dimensions: 0.945,
    roles: 0.833,
    thickness: 1.0,
    dimensions_weight: 0.6,
    roles_weight: 0.25,
    thickness_weight: 0.15,
  });
  assert.deepEqual(
    geometric.map((item) => item.text),
    [
      "Dimensiones: 0.945 (peso 60 %)",
      "Roles: 0.833 (peso 25 %)",
      "Espesor: 1.000 (peso 15 %)",
    ],
  );

  const semantic = formatScoreBreakdown({ cosine: 0.912 });
  assert.deepEqual(semantic.map((item) => item.text), ["Similitud coseno: 0.912"]);

  const joined = [...geometric, ...semantic].map((item) => item.text.toLowerCase()).join(" ");
  assert.equal(joined.includes("probabil"), false);
  assert.deepEqual(formatScoreBreakdown(null), []);
});

test("collectCoincidences derives Spanish coincidence bullets from score_components and descriptors", () => {
  const match = {
    score_components: {
      dimensions: 1.0,
      roles: 0.75,
      thickness: 1.0,
    },
    differences: [{ field: "roles.shelf", query_value: "2", candidate_value: "3" }],
  };
  const candidateDescriptor = {
    descriptor_version: "furniture-v2",
    dimensions: { width_mm: 900, depth_mm: 400, height_mm: 1800 },
    structure: "top_base_between_sides",
    thicknesses_mm: [18.0],
    material: "Melamina blanca",
    finish: null,
  };

  const coincidences = collectCoincidences(match, { candidateDescriptor });
  assert.deepEqual(coincidences, [
    "Mismas dimensiones generales",
    "Mismo espesor (18 mm)",
    "Misma estructura (entre costados)",
    "Mismo material (Melamina blanca)",
  ]);
});

test("collectCoincidences supports V3 table descriptors and excludes differing fields", () => {
  const match = {
    score_components: { dimensions: 0.95, roles: 1.0, thickness: 1.0 },
    differences: [{ field: "dimensions.width_mm", query_value: "1400.0", candidate_value: "1200.0" }],
  };
  const queryDescriptor = {
    descriptor_version: "furniture-v3",
    structure: "side_support_table",
    components: [{ role: "tabletop", quantity: 1, thickness_mm: 25 }],
  };
  const candidateDescriptor = {
    descriptor_version: "furniture-v3",
    structure: "side_support_table",
    components: [{ role: "tabletop", quantity: 1, thickness_mm: 25 }],
  };

  const coincidences = collectCoincidences(match, { queryDescriptor, candidateDescriptor });
  assert.equal(coincidences.includes("Mismas dimensiones generales"), false);
  assert.equal(coincidences.includes("Mismo espesor (25 mm)"), true);
  assert.equal(coincidences.includes("Misma estructura (dos soportes laterales)"), true);
  assert.equal(coincidences.includes("Misma distribución de piezas"), true);
});

test("explainSimilarityMatch combines coincidences, differences, scoreBreakdown and technical lines", () => {
  const match = {
    library_item_id: "item-2",
    run_id: "run-2",
    result_revision: 1,
    method: "geometric",
    score: 0.912,
    score_kind: "geometric_similarity",
    score_components: {
      dimensions: 0.96,
      roles: 0.8,
      thickness: 1.0,
      dimensions_weight: 0.6,
      roles_weight: 0.25,
      thickness_weight: 0.15,
    },
    differences: [
      { field: "dimensions.width_mm", query_value: "900.0", candidate_value: "950.0" },
      { field: "roles.shelf", query_value: "2", candidate_value: "3" },
      { field: "material", query_value: "None", candidate_value: "Haya" },
    ],
  };

  const explained = explainSimilarityMatch(match, {
    candidateDescriptor: {
      descriptor_version: "furniture-v2",
      structure: "top_base_between_sides",
      thicknesses_mm: [18.0],
      material: "Haya",
    },
  });

  assert.equal(explained.methodLabel, "Geométrico offline");
  assert.equal(explained.scoreText, "0.912");
  assert.deepEqual(explained.coincidences, [
    "Mismo espesor (18 mm)",
    "Misma estructura (entre costados)",
  ]);
  assert.deepEqual(explained.differences, [
    "Ancho: 900 mm -> 950 mm (+50 mm)",
    "Baldas: 2 -> 3 (+1)",
    "Material: Desconocido -> Haya",
  ]);
  assert.equal(explained.scoreBreakdown.length, 3);
  assert.equal(explained.technical.length, 3);
});
