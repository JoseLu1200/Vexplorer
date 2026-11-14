import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { presentHistoricalComparables, presentHistoricalEstimate, presentHistoricalRecord, presentHistoryImport, presentProvisionalScenarios } from "../core/history.js";

const pydanticHistory=JSON.parse(readFileSync(new URL("./fixtures/history-contract.json",import.meta.url),"utf8"));
const pydanticScenarios=JSON.parse(readFileSync(new URL("./fixtures/history-scenarios-contract.json",import.meta.url),"utf8"));

test("Pydantic history fixtures preserve nested provenance, formulas, tuples and uncertainty", () => {
  const comparables=presentHistoricalComparables(pydanticHistory.comparables.data),estimate=presentHistoricalEstimate(pydanticHistory.estimate.data);
  assert.equal(comparables.items[0].provenanceLabel,"Registro empresarial real · coste ejecutado");
  assert.equal(comparables.items[1].provenanceLabel,"Fixture sintético · presupuesto");
  assert.match(estimate.hoursLabel,/rango 9,2–14 h/);
  assert.equal(estimate.costUncertaintyLabel,"Incertidumbre de coste alta");
  assert.equal(estimate.hoursUncertaintyLabel,"Incertidumbre de horas alta");
  assert.match(estimate.lines[0].formula,/target_finished_item_quantity/);
  assert.equal(estimate.provenanceLabel,"Base: 1 registro empresarial real · 1 fixture sintético");
});

test("history import reports accepted and rejected rows without hiding errors", () => {
  const result = presentHistoryImport({ import_id: "imp-1", accepted: 7, rejected: 2, errors: [{ row: 4, message: "Horas ausentes" }] });
  assert.equal(result.summary, "7 registros aceptados · 2 rechazados");
  assert.equal(result.errors[0], "Fila 4: Horas ausentes");
});

test("comparables distinguish actual records from synthetic fixtures and retrieval method", () => {
  const result = presentHistoricalComparables({ retrieval_method: "attribute", items: [
    { record: { record_id:"h-1", project_id:"Recepción Norte", origin: "actual", cost_basis:"actual", provenance: { source: "ERP" } }, score: 0.82, differences: ["120 mm más ancho"], missing_fields:[] },
    { record: { record_id:"h-2", project_id:"Fixture demo", origin: "synthetic", provenance: { source: "fixture" } }, score: 0.79, differences: [], missing_fields:[] },
  ] });
  assert.equal(result.methodLabel, "Atributos verificables");
  assert.equal(result.items[0].provenanceLabel, "Registro empresarial real · coste ejecutado");
  assert.equal(result.items[1].provenanceLabel, "Fixture sintético");
});

test("published academic budgets stay separate from enterprise actuals and synthetic fixtures", () => {
  const record=presentHistoricalRecord({origin:"published",cost_basis:"budget",provenance:{source:"Public academic dataset",source_date:"2024-03-01"}});
  assert.equal(record.originLabel,"Fuente pública publicada");
  assert.equal(record.costBasisLabel,"presupuesto");
  assert.equal(record.provenanceLabel,"Fuente pública publicada · presupuesto");
  const estimate=presentHistoricalEstimate({result_provenance:[{record_id:"pub-1",origin:"published",source:"Academic",source_date:"2024-03-01",cost_basis:"budget"}],uncertainty:"high"});
  assert.equal(estimate.provenanceLabel,"Base: 1 fuente pública publicada");
  assert.equal(estimate.provenanceBasisLabel,"Bases económicas: 1 presupuesto");
});

test("semantic comparable presentation exposes the real embedding space", () => {
  const result=presentHistoricalComparables({retrieval_method:"semantic",embedding_space:{model:"text-embedding-3-small",dimensions:1536},items:[]});
  assert.equal(result.methodLabel,"Similitud semántica real");
  assert.deepEqual(result.embeddingSpace,{model:"text-embedding-3-small",dimensions:1536});
  assert.equal(result.embeddingLabel,"text-embedding-3-small · 1536 dimensiones");
});

test("historical estimate exposes hours, uncertainty and missing data without inventing a total", () => {
  const result = presentHistoricalEstimate({
    basis_revision:"general:4:2",currency:"EUR",comparable_ids:["h-1"],result_provenance:[{record_id:"h-1",origin:"actual",source:"ERP",source_date:"2026-11-01",cost_basis:"actual"}],contributors:[{concept_id:"material",formula:"base comparable × factor dimensional",estimated_cost:null,estimated_hours:18.5,missing_data:["finish"]}],manufacturing_hours: 18.5, hours_range: [15, 23], cost_subtotal: null,
    cost_uncertainty:"not_estimable",hours_uncertainty:"high",uncertainty: "high", missing_data: ["Tarifa de acabado"],assumptions:[],scenarios:[],
  });
  assert.equal(result.hoursLabel, "18,5 h · rango 15–23 h");
  assert.equal(result.totalLabel, "Total desconocido");
  assert.deepEqual(result.missingData, ["Tarifa de acabado"]);
  assert.equal(result.provenanceLabel, "Base: 1 registro empresarial real");
  assert.equal(result.provenanceBasisLabel,"Bases económicas: 1 coste ejecutado real");
  assert.equal(result.provenanceDateLabel,"Fechas declaradas por las fuentes: 1 nov 2026; no implican actualización a hoy");
  assert.equal(result.costUncertaintyLabel,"Coste no estimable");
  assert.equal(result.hoursUncertaintyLabel,"Incertidumbre de horas alta");
});

test("cost-only and hours-only provenance remain separated by metric", () => {
  const result=presentHistoricalEstimate({
    cost_uncertainty:"medium",hours_uncertainty:"low",
    result_provenance:[
      {record_id:"budget",origin:"published",source:"Academic budget",source_date:"2024-03-01",cost_basis:"budget",contributes_cost:true,contributes_hours:false,cost_scope:["material"],hours_scope:[]},
      {record_id:"times",origin:"actual",source:"Workshop timer",source_date:"2026-10-10",cost_basis:"actual",contributes_cost:false,contributes_hours:true,cost_scope:[],hours_scope:["labor","machining"]},
    ],
  });
  assert.equal(result.costProvenanceLabel,"Base de coste: 1 fuente pública publicada");
  assert.equal(result.hoursProvenanceLabel,"Base de horas: 1 registro empresarial real");
  assert.equal(result.costBasisLabel,"Bases de coste: 1 presupuesto");
  assert.equal(result.hoursBasisLabel,"Alcance de horas: labor · machining");
  assert.match(result.costDateLabel,/1 mar 2024/);
  assert.doesNotMatch(result.costDateLabel,/10 oct 2026/);
  assert.match(result.hoursDateLabel,/10 oct 2026/);
  assert.doesNotMatch(result.hoursDateLabel,/1 mar 2024/);
});

test("null and blank historical numbers remain unknown instead of becoming zero", () => {
  const result = presentHistoricalEstimate({ manufacturing_hours: null, cost_subtotal: "", result_provenance: [], uncertainty:"not_estimable" });
  assert.equal(result.hoursLabel, "Horas desconocidas");
  assert.equal(result.totalLabel, "Total desconocido");
});

test("Pydantic provisional scenarios remain conditional cards and never become quotes",()=>{
  const result=presentProvisionalScenarios(pydanticScenarios.data),scenario=result.scenarios[0];
  assert.equal(result.statusLabel,"Escenarios provisionales");
  assert.equal(scenario.labelText,"Escenario condicional provisional · no es una cotización");
  assert.equal(scenario.costLabel,"300 EUR");
  assert.equal(scenario.hoursLabel,"10 h");
  assert.equal(scenario.costRangeLabel,"Rango no estimable");
  assert.equal(scenario.costUncertaintyLabel,"Incertidumbre de coste alta");
  assert.equal(scenario.hoursUncertaintyLabel,"Incertidumbre de horas media");
  assert.match(scenario.provenanceLabel,/Fuente pública publicada · presupuesto/);
  assert.match(scenario.conditionLabel,/1 mueble · material oak veneer/);
  assert.equal(scenario.assumptions[0].state,"provisional");
  assert.match(scenario.contributors[0].formula,/target_finished_item_quantity/);
});
