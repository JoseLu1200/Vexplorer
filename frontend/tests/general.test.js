import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { buildGeneralReviewPayload, buildGeneralReviewedComponent, buildManualGeneralProposal, completeGeneralReviewSnapshot, generalBomArtifact, generalDerivedLoadFailure, generalMachineStatusPresentation, generalRunOptions, normaliseGeneralWorkspace, presentGeneralConstructionDimension, presentGeneralConstructionQuantity, presentGeneralDerived, serialiseGeneralBom } from "../core/general.js";

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

test("machine field decisions expose only accepted values while preserving the raw hypothesis",()=>{
  const component={id:"panel-1",label:"Panel",kind:"panel",role:"side",length:{value_mm:800,state:"hypothesis"},width:{value_mm:600,state:"hypothesis"},thickness:{value_mm:18,state:"hypothesis"},quantity:{value:2,state:"hypothesis"},material:{value:"oak",state:"hypothesis"},finish:{value:"oil",state:"hypothesis"},unknown_fields:[]};
  const workspace=normaliseGeneralWorkspace({proposal_revision:1,review_revision:1,status:"reviewed_incomplete",draft:{components:[component]},review:{reviewer_kind:"machine",reviewer_name:"Verifier",components:[component],machine_checks:[
    {id:"accept-length",summary:"La cota longitudinal coincide."},
    {id:"reject-width",summary:"La anchura contradice la vista lateral."},
    {id:"abstain-thickness",summary:"El grosor no es legible."},
    {id:"accept-material",summary:"La anotación identifica roble."},
    {id:"conflict-finish",summary:"Dos vistas muestran acabados incompatibles."},
  ],machine_field_reviews:[
    {target_ref:"component:panel-1.length",status:"accepted",check_ids:["accept-length"]},
    {target_ref:"component:panel-1.width",status:"rejected",check_ids:["reject-width"]},
    {target_ref:"component:panel-1.thickness",status:"abstained",check_ids:["abstain-thickness"]},
    {target_ref:"component:panel-1.material",status:"accepted",check_ids:["accept-material"]},
    {target_ref:"component:panel-1.finish",status:"conflict",check_ids:["conflict-finish"]},
  ],auto_review_status:"incomplete"}});
  const effective=workspace.components[0],raw=workspace.rawComponents[0];
  assert.equal(effective.dimensions.length.value,800);
  assert.equal(effective.material.value,"oak");
  assert.deepEqual([effective.dimensions.width.value,effective.dimensions.thickness.value,effective.quantity.value,effective.finish.value],[null,null,null,null]);
  assert.deepEqual([effective.dimensions.width.state,effective.dimensions.thickness.state,effective.quantity.state,effective.finish.state],["unknown","unknown","unknown","unknown"]);
  assert.equal(effective.dimensions.width.machineReview.status,"rejected");
  assert.equal(effective.dimensions.width.machineReview.checkSummaries[0],"La anchura contradice la vista lateral.");
  assert.equal(effective.quantity.machineReview.status,"unreviewed");
  assert.match(effective.quantity.machineReview.reason,/sin decisión de campo/i);
  assert.deepEqual(effective.unknownFields,["width","thickness","quantity","finish"]);
  assert.deepEqual([raw.dimensions.width.value,raw.dimensions.thickness.value,raw.quantity.value,raw.finish.value],[600,18,2,"oil"]);
});

test("human reviews keep their effective component values without machine masking",()=>{
  const workspace=normaliseGeneralWorkspace({proposal_revision:1,review_revision:1,status:"approved",review:{reviewer_kind:"human",reviewer_name:"Ana",components:[{id:"panel",length:{value_mm:800,state:"confirmed"},width:{value_mm:600,state:"confirmed"},thickness:{value_mm:18,state:"confirmed"},quantity:{value:2,state:"confirmed"},material:{value:"oak",state:"confirmed"},finish:{value:"oil",state:"confirmed"}}]}});
  assert.equal(workspace.components[0].dimensions.width.value,600);
  assert.equal(workspace.components[0].quantity.value,2);
  assert.equal(workspace.components[0].dimensions.width.machineReview,undefined);
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

test("BOM exports select the authoritative exact-snapshot artifact",()=>{
  const derived=presentGeneralDerived({package:{proposal_revision:3,review_revision:2,bom_rows:[],artifacts:[{id:"bom-csv",kind:"bom_csv",filename:"bom.csv",status:"ready",incomplete_reasons:[]},{id:"bom-json",kind:"bom_json",filename:"bom.json",status:"ready",incomplete_reasons:[]}]}});
  assert.equal(generalBomArtifact(derived,"csv").id,"bom-csv");
  assert.equal(generalBomArtifact(derived,"json").id,"bom-json");
  assert.equal(generalBomArtifact(derived,"pdf"),null);
});

test("snapshot conflicts are actionable and never presented as ready",()=>{
  assert.deepEqual(generalDerivedLoadFailure({status:409,message:"revision mismatch"}),{label:"Snapshot desactualizado",message:"La propuesta cambió mientras se cargaban sus derivados. Recarga la ejecución para consultar el snapshot exacto. revision mismatch"});
  assert.equal(generalDerivedLoadFailure({status:404}),null);
});

test("accepted construction estimates stay numeric but visibly approximate", () => {
  const dimension=presentGeneralConstructionDimension({
    value_mm:18,
    range_mm:{min_mm:16,max_mm:20},
    state:"estimated",
    method:"catalog_prior",
    formula:"thickness = catalog_prior(panel)",
    operand_refs:["piece:side"],
    source_refs:["view:front"],
    assumption_refs:["assumption:board-thickness"],
    review_status:"accepted",
    explanation:"Espesor habitual compatible con el canto visible.",
  });

  assert.equal(dimension.value,18);
  assert.equal(dimension.display,"≈ 18 mm");
  assert.equal(dimension.rangeDisplay,"16–20 mm");
  assert.equal(dimension.stateLabel,"Estimada");
  assert.equal(dimension.formula,"thickness = catalog_prior(panel)");
  assert.deepEqual(dimension.sourceRefs,["view:front"]);
});

test("accepted estimated quantity remains visibly provisional",()=>{
  const quantity=presentGeneralConstructionQuantity({value:2,min_value:1,max_value:3,state:"estimated",review_status:"accepted",method:"symmetry",source_refs:["view:front"],assumption_refs:["assumption:pair"],explanation:"Par simétrico probable."});
  assert.equal(quantity.display,"≈ 2 uds.");
  assert.equal(quantity.rangeDisplay,"1–3 uds.");
  assert.deepEqual(quantity.assumptionRefs,["assumption:pair"]);
  assert.equal(presentGeneralConstructionQuantity({...quantity,review_status:"rejected"}).value,null);
});

test("derived BOM and CSV retain construction basis, range and references",()=>{
  const derived=presentGeneralDerived({package:{bom_rows:[{
    component_id:"side",label:"Costado",role:"side",
    length:{value_mm:720,state:"estimated",range_mm:{min_mm:710,max_mm:730},method:"construction_assumption",source_refs:["view:front"],assumption_refs:["assumption:clearance"],review_status:"accepted"},
  }]}});
  const length=derived.bom[0].length,csv=serialiseGeneralBom(derived.bom,"csv");
  assert.deepEqual(length.range,{min:710,max:730});
  assert.equal(length.method,"construction_assumption");
  assert.deepEqual(length.sourceRefs,["view:front"]);
  assert.match(csv,/length_state,length_range_min_mm,length_range_max_mm,length_method,length_source_refs,length_assumption_refs/);
  assert.match(csv,/720,estimated,710,730,construction_assumption,view:front,assumption:clearance/);
});

test("construction plan links its ranked decisions, pieces and sheets",()=>{
  const result=presentGeneralDerived({package:{proposal_revision:2,review_revision:1,bom_rows:[],artifacts:[],construction:{
    run_id:"run-1",proposal_revision:2,review_revision:1,basis_revision:"run:run-1:proposal:2:review:1:scenario:base",scenario_id:"base",authority:"provisional_not_manufacturing",
    summary:{label:"Armario de dos costados",component_count:1,occurrence_count:2,source_refs:["view:front"],top_decision_ids:["decision-thickness"],warnings:[]},
    pieces:[{piece_id:"piece-side",component_id:"side",scenario_id:"base",label:"Costado",role:"side",quantity:{value:2,min_value:2,max_value:2,state:"estimated",review_status:"accepted",method:"symmetry",source_refs:["view:front"],assumption_refs:["assumption:symmetry"],explanation:"Par simétrico."},occurrence_ids:[],scenario_occurrence_ids:["scenario:side:1","scenario:side:2"],geometry:{shape_kind:"rectangle",source_contour_ids:["contour:1"],basis_refs:["view:front"],rationale:"Contorno rectangular."},length:{value_mm:720,range_mm:{min_mm:710,max_mm:730},state:"estimated",review_status:"accepted",method:"fit",formula:null,operand_refs:[],source_refs:["view:front"],assumption_refs:["assumption:clearance"],explanation:"Ajuste al hueco."},width:{value_mm:500,range_mm:null,state:"observed",review_status:"accepted",method:"observed_copy",formula:null,operand_refs:[],source_refs:["dimension:d1"],assumption_refs:[],explanation:"Cota visible."},thickness:{value_mm:null,range_mm:null,state:"unknown",review_status:"abstained",method:null,formula:null,operand_refs:[],source_refs:[],assumption_refs:[],explanation:"Sin respaldo."},detail_ids:[],source_refs:["view:front"],sheet_ids:["sheet-side"]}],
    placements:[],details:[],decisions:[{id:"decision-thickness",category:"dimension",summary:"Espesor de tablero estimado",target_refs:["component:side.thickness"],basis_refs:["assumption:board"],alternatives:["16 mm","19 mm"],rationale:"Afecta uniones y huecos.",impact:"high"}],warnings:[],sheets:[{sheet_id:"sheet-side",kind:"piece",piece_id:"piece-side",title:"Costado",primitives:[],warnings:[]}]}}});
  assert.equal(result.construction.pieces[0].length.display,"≈ 720 mm");
  assert.equal(result.construction.pieces[0].thickness.value,null);
  assert.equal(result.construction.topDecisions[0].id,"decision-thickness");
  assert.equal(result.construction.sheets[0].pieceId,"piece-side");
});

test("non-accepted construction values are not promoted into the primary BOM", () => {
  for(const review_status of ["rejected","conflict","abstained","unreviewed"]){
    const dimension=presentGeneralConstructionDimension({value_mm:18,state:"estimated",review_status,explanation:"Sin respaldo suficiente."});
    assert.equal(dimension.value,null);
    assert.equal(dimension.display,"Desconocida");
    assert.equal(dimension.reviewStatus,review_status);
    assert.equal(dimension.explanation,"Sin respaldo suficiente.");
  }
});

test("BOM exports preserve unknown values as empty cells", () => {
  const bom=[{component_id:"panel-1",occurrence_ids:["occ-1"],quantity:{value:1,state:"confirmed"},material:{value:null,state:"unknown"},dimensions:{length:{value:720},width:{value:null},thickness:{value:19}}}];
  assert.deepEqual(JSON.parse(serialiseGeneralBom(bom,"json")),bom);
  const csv=serialiseGeneralBom(bom,"csv");
  assert.match(csv,/component_id,label,role,quantity,quantity_state/);
  assert.match(csv,/panel-1,,,1,confirmed,unknown,occ-1,,720/);
  assert.doesNotMatch(csv,/undefined|null/);
});

test("machine BOM export uses the backend masked projection and retains decision reasons",()=>{
  const derived=presentGeneralDerived({package:{bom_rows:[{component_id:"panel-1",label:"Panel",role:"side",quantity:{value:null,state:"unknown"},length:{value_mm:800,state:"hypothesis"},width:{value_mm:null,state:"unknown"},thickness:{value_mm:null,state:"unknown"},material:{value:"oak",state:"hypothesis"},finish:{value:null,state:"unknown"},machine_field_reviews:[
    {field:"length",target_ref:"component:panel-1.length",status:"accepted",check_ids:["length-ok"],check_summaries:["La cota coincide."],source_refs:["dimension:d-1"]},
    {field:"width",target_ref:"component:panel-1.width",status:"rejected",check_ids:["width-fail"],check_summaries:["La vista lateral contradice el valor."],source_refs:["view:side"]},
    {field:"thickness",target_ref:"component:panel-1.thickness",status:"abstained",check_ids:["thickness-unknown"],check_summaries:["El grosor no es legible."],source_refs:["view:front"]},
    {field:"quantity",target_ref:"component:panel-1.quantity",status:"unreviewed",check_ids:[],check_summaries:[],source_refs:[]},
  ]}]}});
  const row=derived.bom[0],csv=serialiseGeneralBom(derived.bom,"csv"),json=JSON.parse(serialiseGeneralBom(derived.bom,"json"));
  assert.equal(row.machineFieldReviews[1].status,"rejected");
  assert.equal(row.machineFieldReviews[1].checkSummaries[0],"La vista lateral contradice el valor.");
  assert.match(csv,/panel-1,Panel,side,,unknown,unknown,,,800,hypothesis/);
  assert.match(csv,/,oak,$/);
  assert.doesNotMatch(csv,/600|,18,|,2,/);
  assert.equal(json[0].width.value,null);
  assert.equal(json[0].machineFieldReviews[2].status,"abstained");
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
