import test from "node:test";
import assert from "node:assert/strict";
import { cameraZoomPosition, generalCatalogScene, generalSceneSelection, normaliseScene, sceneLoadPlan, sceneMeshCenter } from "../core/scene.js";
import { observeContainerSize, resizeRendererToContainer } from "../components/SceneViewer.js";

test("scene refuses objects with incomplete dimensions instead of inventing geometry", () => {
  const scene = normaliseScene({ state: "incomplete", warnings: ["Falta grosor"], objects: [
    { piece_id: "p1", label: "Lateral", position_mm: { x: 0, y: 0, z: 0 }, dimensions_mm: { x: 300, y: 1200, z: null } },
  ] });
  assert.equal(scene.objects.length, 0);
  assert.match(scene.warnings.join(" "), /Falta grosor/);
});

test("scene keeps backed occurrences and their evidence identifiers", () => {
  const scene = normaliseScene({ state: "ready", objects: [
    { piece_id: "p1", proposal_id: "c1", occurrence_index: 2, position_mm: { x: 0, y: 1, z: 2 }, dimensions_mm: { x: 300, y: 1200, z: 18 }, evidence_ids: ["ev1"], placement_basis: "review" },
  ] });
  assert.equal(scene.objects[0].key, "p1:2");
  assert.deepEqual(scene.objects[0].dimensions, [300, 1200, 18]);
  assert.deepEqual(scene.objects[0].evidenceIds, ["ev1"]);
  assert.deepEqual(sceneMeshCenter(scene.objects[0]), [150, 601, 11]);
});

test("parts-only scene preserves observation, placement state and assumptions", () => {
  const scene = normaliseScene({ state: "ready", assumptions: ["Reconstrucción derivada"], objects: [{
    piece_id: "piece-1", proposal_id: "candidate-1", part_observation_id: "part-obs-A", occurrence_index: 1,
    position_mm: { x: 0, y: 0, z: 0 }, dimensions_mm: { x: 900, y: 300, z: 18 },
    placement_status: "hypothesis", placement_constraint_ids: ["constraint-1"], placement_basis: "candidate",
  }] });
  assert.equal(scene.objects[0].partObservationId, "part-obs-A");
  assert.equal(scene.objects[0].placementStatus, "hypothesis");
  assert.deepEqual(scene.objects[0].placementConstraintIds, ["constraint-1"]);
  assert.deepEqual(scene.assumptions, ["Reconstrucción derivada"]);
});

test("3D toolbar zoom keeps the orbit target and moves the camera", () => {
  assert.deepEqual(cameraZoomPosition([100, 50, 100], [20, 10, 20], .5), [60, 30, 60]);
});

test("3D viewer follows container reflow and stops observing after disposal", () => {
  const observed = [];
  const disconnected = [];
  let notify;
  class FakeResizeObserver {
    constructor(callback) { notify = callback; }
    observe(element) { observed.push(element); }
    disconnect() { disconnected.push(true); }
  }
  const root = { id: "scene-root" };
  let resizeCount = 0;

  const stop = observeContainerSize(root, () => { resizeCount += 1; }, FakeResizeObserver);
  assert.deepEqual(observed, [root]);
  assert.equal(resizeCount, 1, "the initial canvas size is synchronized immediately");

  notify();
  assert.equal(resizeCount, 2, "layout-only changes synchronize the renderer without a window resize");

  stop();
  assert.deepEqual(disconnected, [true]);
});

test("3D viewer keeps its last valid projection while hidden and resizes when visible again", () => {
  let rect = { width: 0, height: 0 };
  const sizes = [];
  let projectionUpdates = 0;
  let draws = 0;
  const root = { getBoundingClientRect: () => rect };
  const renderer = { setSize: (...size) => sizes.push(size) };
  const camera = { aspect: 1, updateProjectionMatrix: () => { projectionUpdates += 1; } };

  assert.equal(resizeRendererToContainer(root, renderer, camera, () => { draws += 1; }), false);
  assert.deepEqual(sizes, []);
  assert.equal(camera.aspect, 1);

  rect = { width: 900, height: 450 };
  assert.equal(resizeRendererToContainer(root, renderer, camera, () => { draws += 1; }), true);
  assert.deepEqual(sizes, [[900, 450, false]]);
  assert.equal(camera.aspect, 2);
  assert.equal(projectionUpdates, 1);
  assert.equal(draws, 1);
});

const accepted=(field)=>({field,status:"accepted",targetRef:`component:panel.${field}`,checkIds:[`${field}-ok`],checkSummaries:[`${field} coherente`],sourceRefs:["view:front"]});

test("general scene becomes an explicitly non-physical catalogue from accepted dimensions and occurrences",()=>{
  const scene=generalCatalogScene({scene:{status:"schematic_ready",warnings:["Representación esquemática."],items:[{component_id:"panel",occurrence_ids:[],scenario_occurrence_ids:["scenario:panel:1","scenario:panel:2"],occurrence_status:"provisional",length:{value_mm:800},width:{value_mm:400},thickness:{value_mm:18}}]},bom:[{componentId:"panel",label:"Panel",role:"side",machineFieldReviews:[accepted("length"),accepted("width"),accepted("thickness"),accepted("quantity")],sourceEvidenceIds:["ev-1"]}]},{reviewerKind:"machine"});
  const model=normaliseScene(scene);
  assert.equal(model.objects.length,2);
  assert.deepEqual(model.objects[0].dimensions,[800,400,18]);
  assert.equal(model.objects[0].pieceId,"scenario:panel:1");
  assert.equal(model.objects[0].proposalId,"panel");
  assert.equal(model.objects[0].placementBasis,"catalogue_visualisation_not_physical");
  assert.match(model.assumptions.join(" "),/catálogo de piezas separadas.*no representa un montaje físico/i);
  assert.notDeepEqual(model.objects[0].position,model.objects[1].position);
});

test("general scene omits provisional occurrences when machine quantity was rejected",()=>{
  const scene=generalCatalogScene({scene:{status:"schematic_incomplete",warnings:[],items:[{component_id:"panel",occurrence_ids:[],scenario_occurrence_ids:["scenario:panel:1"],occurrence_status:"provisional",length:{value_mm:800},width:{value_mm:400},thickness:{value_mm:18}}]},bom:[{componentId:"panel",machineFieldReviews:[accepted("length"),accepted("width"),accepted("thickness"),{...accepted("quantity"),status:"rejected",checkSummaries:["Cantidad no respaldada"]}]}]},{reviewerKind:"machine"});
  assert.equal(scene.objects.length,0);
  assert.match(scene.warnings.join(" "),/cantidad rechazada/i);
  assert.doesNotMatch(scene.warnings.join(" "),/\brejected\b/i);
});

test("general scene omits a component without a known accepted thickness instead of inventing it",()=>{
  const scene=generalCatalogScene({scene:{status:"schematic_incomplete",warnings:[],items:[{component_id:"panel",occurrence_ids:["occ-1"],scenario_occurrence_ids:[],occurrence_status:"confirmed",length:{value_mm:800},width:{value_mm:400},thickness:{value_mm:null}}]},bom:[{componentId:"panel",machineFieldReviews:[accepted("length"),accepted("width"),{...accepted("thickness"),status:"abstained",checkSummaries:["Grosor ilegible"]}]}]},{reviewerKind:"machine"});
  assert.equal(scene.objects.length,0);
  assert.match(scene.warnings.join(" "),/grosor.*ilegible|grosor.*desconocido/i);
  assert.doesNotMatch(scene.warnings.join(" "),/revisión humana/i);
});

test("scene routing uses exact general revisions and keeps legacy result revisions separate",()=>{
  const general=sceneLoadPlan({runId:"run-1",resultRevision:99,generalWorkspace:{isGeneral:true,proposalRevision:4,reviewRevision:2,reviewerKind:"machine"},generalDerived:{proposalRevision:4,reviewRevision:2,scene:{items:[],warnings:[]},bom:[]}});
  assert.equal(general.kind,"general");
  assert.equal(general.identity,"run-1:general:4:2");
  assert.equal(general.fetchLegacy,false);
  const legacy=sceneLoadPlan({runId:"run-2",resultRevision:7,generalWorkspace:null,generalDerived:null});
  assert.deepEqual(legacy,{kind:"legacy",identity:"run-2:legacy:7",fetchLegacy:true,scene:null});
  const stale=sceneLoadPlan({runId:"run-1",resultRevision:99,generalWorkspace:{isGeneral:true,proposalRevision:4,reviewRevision:3,reviewerKind:"machine"},generalDerived:{proposalRevision:4,reviewRevision:2,scene:{items:[{component_id:"panel"}]},bom:[]}});
  assert.equal(stale.identity,"run-1:general:4:3");
  assert.equal(stale.scene.objects.length,0);
  assert.match(stale.scene.warnings[0],/no corresponde al snapshot general actual/i);
});

test("general scene selection resolves an occurrence through its component proposal id",()=>{
  const component={id:"panel",label:"Panel aceptado"},workspace={components:[component]};
  assert.equal(generalSceneSelection(workspace,{pieceId:"scenario:panel:1",proposalId:"panel"}),component);
  assert.equal(generalSceneSelection(workspace,{pieceId:"scenario:other:1",proposalId:"other"}),null);
});
