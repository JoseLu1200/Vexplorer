import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { buildGeneralReviewPayload, buildGeneralReviewedComponent, buildManualGeneralProposal, completeGeneralReviewSnapshot, generalMachineStatusPresentation, generalRunOptions, normaliseGeneralWorkspace, presentGeneralDerived, serialiseGeneralBom } from "../core/general.js";

const pydanticRecord=JSON.parse(readFileSync(new URL("./fixtures/general-record.json",import.meta.url),"utf8"));

test("router-generated Pydantic record uses draft values instead of proposal binding ids", () => {
  assert.equal(pydanticRecord.schema_version,"0.6.0");
  const workspace=normaliseGeneralWorkspace(pydanticRecord.data);
  assert.equal(workspace.components[0].dimensions.length.value,800);
  assert.equal(workspace.components[0].dimensions.length.state,"hypothesis");
  assert.deepEqual(workspace.components[0].dimensions.length.dependencyRefs,["binding:width"]);
  assert.equal(workspace.components[0].dimensions.width.value,null);
});

test("general live runs request one model-generated autonomous workflow", () => {
  assert.deepEqual(generalRunOptions("live"),{proposal_mode:"model_generated"});
  assert.deepEqual(generalRunOptions("geometry_only"),{proposal_mode:"none"});
});

test("machine review provenance stays distinct from optional human correction", () => {
  const workspace=normaliseGeneralWorkspace({proposal_revision:2,review_revision:1,status:"reviewed_incomplete",draft:{drawing_id:"d",ledger_revision:"l",components:[]},review:{reviewer_kind:"machine",reviewer_name:"Vexplorer verifier",machine_provenance:{model:"gpt-6",policy_version:"general-auto-review-v1",response_ids:["resp-1"],review_relation:"separate_model"},machine_checks:[{id:"geometry",kind:"visual_consistency",outcome:"pass",method:"model_visual",target_refs:["component:panel-1"],source_refs:["drawing:front"],summary:"La silueta coincide."}],auto_review_status:"incomplete",components:[]}});
  assert.equal(workspace.reviewerKind,"machine");
  assert.equal(workspace.machineProvenance.model,"gpt-6");
  assert.equal(workspace.autoReviewStatus,"incomplete");
  assert.equal(workspace.autoChecks[0].summary,"La silueta coincide.");
});

test("a stored machine review removes mandatory human-review copy from the run header",()=>{
  assert.deepEqual(generalMachineStatusPresentation({reviewerKind:"machine",autoReviewStatus:"accepted",status:"approved"}),{
    label:"Auto-revisión completada",
    message:"La revisión automática de coherencia terminó. Puedes consultar resultados, descargas y escenarios sin una aprobación humana obligatoria.",
  });
  assert.deepEqual(generalMachineStatusPresentation({reviewerKind:"machine",autoReviewStatus:"incomplete",status:"reviewed_incomplete"}),{
    label:"Auto-revisión con incógnitas",
    message:"La revisión automática terminó con datos desconocidos. Los resultados siguen disponibles y conservan esas incógnitas; la corrección humana es opcional.",
  });
  assert.equal(generalMachineStatusPresentation({reviewerKind:"human",status:"approved"}),null);
});

test("general components preserve evidence, unknowns and physical occurrences", () => {
  const workspace = normaliseGeneralWorkspace({
    proposal_revision: 4, review_revision: 0,
    status: "needs_review",
    draft: {
      components: [{
        id: "panel-1", label: "Costado", kind: "panel",
        source_view_ids: ["front"], source_observation_ids: ["obs-1"], source_evidence_ids: ["ev-1"], source_dimension_ids: ["dim-1"],
        length: { value_mm: 720, state: "observed", evidence_ids:["ev-1"] }, width: { value_mm: null, state: "unknown" }, thickness:{value_mm:null,state:"unknown"},
        quantity: { value: null, state: "unknown" }, assumptions: [{ id: "a-1", label: "Orientación", state: "proposed" }], unknown_fields: ["width", "quantity"],
      }],
    },
    review:{occurrences: [{ id: "occ-1", component_id: "panel-1", occurrence_index:1 }]},
  });

  assert.equal(workspace.proposalRevision, 4);
  assert.equal(workspace.components[0].dimensions.width.value, null);
  assert.deepEqual(workspace.components[0].unknownFields, ["width", "quantity"]);
  assert.deepEqual(workspace.components[0].evidenceIds, ["ev-1"]);
  assert.equal(workspace.occurrences[0].componentId, "panel-1");
});

test("general review sends only explicit replace split or merge operations", () => {
  const components=[{id:"panel-left",replaces_component_ids:["panel-1"]},{id:"panel-right",replaces_component_ids:["panel-1"]}];
  const payload = buildGeneralReviewPayload({ proposalRevision: 4, reviewRevision: 1 }, {
    reviewerName: "ana", reason: "El alzado separa dos costados.",
    operations: [{ kind: "split", sourceComponentIds: ["panel-1"], resultComponentIds: ["panel-left","panel-right"], reason:"Separación confirmada" }], components,
  });

  assert.equal(payload.base_proposal_revision, 4);
  assert.equal(payload.base_review_revision, 1);
  assert.equal(payload.reviewer_name, "ana");
  assert.deepEqual(payload.operations[0].source_component_ids, ["panel-1"]);
  assert.deepEqual(payload.operations[0].result_component_ids, ["panel-left","panel-right"]);
  assert.equal(payload.operations[0].kind, "split");
  assert.deepEqual(payload.components,components);
  assert.equal(payload.furniture_quantity.state,"unknown");
});

test("derived BOM keeps missing fields and incomplete artifacts visible", () => {
  const result = presentGeneralDerived({ historical_target:{family:"cabinet",basis_revision:"general:4:2"}, package:{
    proposal_revision: 4, review_revision:2,
    bom_rows: [{ component_id: "panel-1", occurrence_ids: ["occ-1"], quantity: { value: 1, state: "confirmed" }, material: { value: null, state: "unknown" } }],
    artifacts: [{ id: "sheet-1", kind: "drawing_svg", status: "incomplete", incomplete_reasons: ["Falta grosor"] }],
    cost_basis: { status: "partial", missing_data: ["material"], contributors: [] },
  }
  });

  assert.equal(result.bom[0].material.value, null);
  assert.deepEqual(result.artifacts[0].incompleteReasons, ["Falta grosor"]);
  assert.deepEqual(result.costBasis.missingData, ["material"]);
  assert.deepEqual(result.historicalTarget,{family:"cabinet",basis_revision:"general:4:2"});
});

test("BOM exports preserve unknown values as empty cells", () => {
  const bom=[{component_id:"panel-1",occurrence_ids:["occ-1"],quantity:{value:1,state:"confirmed"},material:{value:null,state:"unknown"},dimensions:{length:{value:720},width:{value:null},thickness:{value:19}}}];
  assert.deepEqual(JSON.parse(serialiseGeneralBom(bom,"json")),bom);
  assert.equal(serialiseGeneralBom(bom,"csv"),"component_id,label,role,quantity,quantity_state,occurrence_status,physical_occurrence_ids,scenario_occurrence_ids,length_mm,width_mm,thickness_mm,material,finish\r\npanel-1,,,1,confirmed,unknown,occ-1,,720,,19,,");
});

test("provisional BOM exports keep scenario occurrences distinct from confirmed physical ones",()=>{
  const derived=presentGeneralDerived({package:{bom_rows:[{component_id:"side",label:"=Side",role:"side",occurrence_ids:[],scenario_occurrence_ids:["scenario:side:1","scenario:side:2"],occurrence_status:"provisional",quantity:{value:2,state:"hypothesis"},length:{value_mm:700},width:{value_mm:500},thickness:{value_mm:19},material:{value:"MDF"},finish:{value:null}}]}});
  assert.deepEqual(derived.bom[0].scenarioOccurrenceIds,["scenario:side:1","scenario:side:2"]);
  assert.equal(derived.bom[0].occurrenceStatus,"provisional");
  const csv=serialiseGeneralBom(derived.bom,"csv");
  assert.match(csv,/quantity_state,occurrence_status,physical_occurrence_ids,scenario_occurrence_ids/);
  assert.match(csv,/side,'=Side,side,2,hypothesis,provisional,,scenario:side:1\|scenario:side:2/);
});

test("manual general proposal starts with unknown measurements instead of invented values", () => {
  const proposal=buildManualGeneralProposal({drawingId:"drawing-1",ledgerRevision:"candidate-7",label:"Costado",kind:"panel",role:"side_panel",reason:"Componente identificado por revisión humana",idFactory:(kind)=>`${kind}-1`});
  assert.equal(proposal.proposal_origin,"human");
  assert.equal(proposal.ledger_revision,"candidate-7");
  assert.equal(proposal.components[0].quantity.value,null);
  assert.equal(proposal.components[0].length_binding_id,null);
  assert.deepEqual(proposal.components[0].unknown_fields,["length","width","thickness","quantity","material","finish","placement"]);
});

test("review preserves unchanged Pydantic hypothesis provenance and marks only human edits confirmed", () => {
  const source={id:"panel",label:"Panel",kind:"panel",role:"unknown",dimensions:{length:{value:800,state:"hypothesis",dependencyRefs:["binding:width"],evidenceIds:["e-1"],dimensionIds:["d-1"]},width:{value:null,state:"unknown"},thickness:{value:null,state:"unknown"}},quantity:{value:null,state:"unknown"},material:{value:null,state:"unknown"},finish:{value:null,state:"unknown"},viewIds:["front"],observationIds:[],contourIds:[],evidenceIds:["e-1"],dimensionIds:["d-1"],documentRefs:[]};
  const result=buildGeneralReviewedComponent({sourceComponents:[source],resultId:"panel-reviewed",values:{label:"Panel",kind:"panel",role:"side",length:"800",width:"",thickness:"18",quantity:"2",material:"roble",finish:""},reason:"Revisión humana",humanRef:"human:ana"});
  assert.equal(result.length.state,"hypothesis");
  assert.deepEqual(result.length.dependency_refs,["binding:width"]);
  assert.equal(result.thickness.state,"confirmed");
  assert.deepEqual(result.thickness.dependency_refs,["human:ana"]);
  assert.deepEqual(result.quantity.dependency_refs,["human:ana"]);
  assert.deepEqual(result.material.dependency_refs,["human:ana"]);
  assert.ok(result.unknown_fields.includes("placement"));
});

test("review snapshot carries every unedited source and keeps finished furniture quantity separate", () => {
  const source=(id)=>({id,label:id,kind:"panel",role:"unknown",dimensions:{length:{value:null,state:"unknown"},width:{value:null,state:"unknown"},thickness:{value:null,state:"unknown"}},quantity:{value:null,state:"unknown"},material:{value:null,state:"unknown"},finish:{value:null,state:"unknown"},viewIds:[],observationIds:[],contourIds:[],evidenceIds:[],dimensionIds:[],documentRefs:[]});
  const workspace={proposalRevision:1,reviewRevision:0,components:[source("a"),source("b")]},edited=buildGeneralReviewedComponent({sourceComponents:[workspace.components[0]],resultId:"a-reviewed",values:{label:"a",kind:"panel",role:"side",quantity:"",length:"",width:"",thickness:"",material:"",finish:""},reason:"Revisión",humanRef:"human:ana"});
  const complete=completeGeneralReviewSnapshot(workspace,{operations:[{kind:"replace",sourceComponentIds:["a"],resultComponentIds:["a-reviewed"],reason:"Revisión"}],components:[edited],reason:"Revisión",humanRef:"human:ana"});
  const payload=buildGeneralReviewPayload(workspace,{reviewerName:"ana",reason:"Revisión",...complete,furnitureQuantity:"1",currency:"EUR",requiredCostScope:["material","labor"],requiredHoursScope:["labor","machining"],humanRef:"human:ana"});
  assert.deepEqual(payload.operations.flatMap((item)=>item.source_component_ids).sort(),["a","b"]);
  assert.equal(payload.components.length,2);
  assert.deepEqual(payload.furniture_quantity,{value:1,state:"confirmed",dependency_refs:["human:ana"],evidence_ids:[]});
  assert.equal(payload.currency,"EUR");
  assert.deepEqual(payload.required_cost_scope,["material","labor"]);
  assert.deepEqual(payload.required_hours_scope,["labor","machining"]);
});
