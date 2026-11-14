import test from "node:test";
import assert from "node:assert/strict";
import * as sceneTools from "../core/scene.js";
import * as viewerTools from "../components/SceneViewer.js";
import { cameraZoomPosition, normaliseScene, sceneMeshCenter } from "../core/scene.js";
import { observeContainerSize, resizeRendererToContainer } from "../components/SceneViewer.js";

test("general furniture renders an explicitly unplaced layout without fabricating unknown thickness or occurrences", () => {
  assert.equal(typeof sceneTools.generalSceneForViewer, "function");
  const field=(value_mm)=>({value_mm,state:value_mm===null?"unknown":"hypothesis"});
  const scene=sceneTools.generalSceneForViewer({items:[
    {component_id:"top",length:field(1200),width:field(700),thickness:field(null),occurrence_ids:[]},
    {component_id:"side",length:field(720),width:field(700),thickness:field(18),occurrence_ids:["s1","s2"]},
    {component_id:"unknown",length:field(null),width:field(500),thickness:field(null)},
  ]});
  assert.equal(scene.objects.length,2);
  assert.equal(scene.objects[0].render_kind,"surface");
  assert.equal(scene.objects[0].dimensions_mm.z,0);
  assert.equal(scene.objects[1].dimensions_mm.z,18);
  assert.equal(scene.objects[0].placement_basis,"display_layout_not_assembly");
  assert.equal(scene.collision_status,"not_applicable");
  assert.match(scene.warnings.join(" "),/1.*largo.*ancho/);
  assert.equal(sceneTools.normaliseScene(scene).objects.length,2);
  assert.equal(sceneTools.normaliseScene(scene).objects[0].renderKind,"surface");
});

test("mounted general scene renders every placed occurrence instead of the legacy type grid", () => {
  const field=(value_mm)=>({value_mm,state:"hypothesis"});
  const raw=sceneTools.generalSceneForViewer({status:"mounted_hypothesis",warnings:["Hipótesis geométrica"],items:[
    {component_id:"shelf",occurrence_id:"provisional:shelf-1",occurrence_index:1,occurrence_status:"provisional",scenario_occurrence_ids:["provisional:shelf-1"],length:field(100),width:field(40),thickness:field(10),position_mm:{x:5,y:6,z:7},orientation:{length_axis:"-y",width_axis:"+z",thickness_axis:"-x"},status:"placed_hypothesis"},
    {component_id:"shelf",occurrence_id:"shelf-2",occurrence_index:2,length:field(100),width:field(40),thickness:field(10),position_mm:{x:105,y:6,z:7},orientation:{length_axis:"-y",width_axis:"+z",thickness_axis:"-x"},status:"placed_hypothesis"},
  ]});

  assert.equal(raw.display_layout,false);
  assert.equal(raw.state,"mounted_hypothesis");
  assert.deepEqual(raw.objects.map((item)=>item.occurrence_id),["provisional:shelf-1","shelf-2"]);
  assert.deepEqual(sceneTools.normaliseScene(raw).objects.map((item)=>item.key),["provisional:shelf-1","shelf-2"]);
  assert.match(raw.warnings.join(" "),/Hipótesis geométrica/);
});

test("mounted scene preserves the server-validated world AABB size for its center", () => {
  const field=(value_mm)=>({value_mm,state:"hypothesis"});
  const raw=sceneTools.generalSceneForViewer({status:"mounted_hypothesis",items:[{
    component_id:"shelf",occurrence_id:"shelf-tolerated",occurrence_index:1,
    length:field(100),width:field(40),thickness:field(10),position_mm:{x:5,y:6,z:7},
    size_mm:{x:10.4,y:100.6,z:40.2},
    orientation:{length_axis:"-y",width_axis:"+z",thickness_axis:"-x"},status:"placed_hypothesis",
  }]});
  const item=sceneTools.normaliseScene(raw).objects[0];

  assert.deepEqual(item.dimensions,[100,40,10],"the mesh remains in component-local axes");
  assert.deepEqual(item.worldDimensions,[10.4,100.6,40.2],"validated AABB extent stays server-authoritative");
  assert.deepEqual(sceneMeshCenter(item),[10.2,56.3,27.1]);
});

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

test("mounted furniture keeps local panel dimensions and applies its proper signed-axis rotation", () => {
  assert.equal(typeof sceneTools.sceneMeshTransform, "function");
  const model = normaliseScene({ state: "mounted_hypothesis", objects: [{
    piece_id: "shelf",
    occurrence_id: "shelf-3",
    occurrence_index: 2,
    dimensions_mm: { x: 100, y: 40, z: 10 },
    position_mm: { x: 5, y: 6, z: 7 },
    orientation: { length_axis: "-y", width_axis: "+z", thickness_axis: "-x" },
    placement_status: "placed_hypothesis",
  }] });

  assert.equal(model.objects.length, 1);
  assert.deepEqual(model.objects[0].dimensions, [100, 40, 10], "box geometry stays in length/width/thickness axes");
  assert.deepEqual(model.objects[0].worldDimensions, [10, 100, 40]);
  assert.deepEqual(sceneTools.sceneMeshTransform(model.objects[0]), {
    center: [10, 56, 27],
    rotationMatrix: [0, 0, -1, -1, 0, 0, 0, 1, 0],
  });
  assert.equal(model.objects[0].key, "shelf-3");
  assert.equal(model.objects[0].occurrenceIndex, 2);
});

test("viewer applies the signed orientation matrix to the mesh around the world AABB center", () => {
  assert.equal(typeof viewerTools.applySceneMeshTransform, "function");
  const calls = {};
  class FakeMatrix4 { set(...values) { this.values = values; return this; } }
  const mesh = {
    position: { set: (...values) => { calls.position = values; } },
    setRotationFromMatrix: (matrix) => { calls.matrix = matrix.values; },
  };
  viewerTools.applySceneMeshTransform(mesh, {
    position: [5, 6, 7], dimensions: [100, 40, 10], worldDimensions: [10, 100, 40],
    rotationMatrix: [0, 0, -1, -1, 0, 0, 0, 1, 0],
  }, FakeMatrix4);

  assert.deepEqual(calls.position, [10, 56, 27]);
  assert.deepEqual(calls.matrix, [0, 0, -1, 0, -1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1]);
});

test("one global Z-up display transform preserves relative centers and local evaluation payload", () => {
  assert.equal(typeof sceneTools.sceneForDisplayUp,"function");
  const raw={objects:[
    {piece_id:"a",occurrence_id:"a-1",dimensions_mm:{x:100,y:200,z:300},position_mm:{x:10,y:20,z:30},orientation:{length_axis:"+x",width_axis:"+y",thickness_axis:"+z"}},
    {piece_id:"b",occurrence_id:"b-1",dimensions_mm:{x:50,y:60,z:70},position_mm:{x:210,y:320,z:430},orientation:{length_axis:"+x",width_axis:"+y",thickness_axis:"+z"}},
  ]};
  const evaluated=normaliseScene(raw),original=structuredClone(evaluated),display=sceneTools.sceneForDisplayUp(evaluated,"z");

  assert.deepEqual(evaluated,original,"display choice never mutates server/evaluation coordinates");
  assert.deepEqual(display.objects[0].position,[10,30,-220]);
  assert.deepEqual(display.objects[0].worldDimensions,[100,300,200]);
  assert.deepEqual(sceneMeshCenter(display.objects[0]),[60,180,-120]);
  assert.deepEqual(display.objects[0].rotationMatrix,[1,0,0,0,0,1,0,-1,0]);
  const sourceDelta=sceneMeshCenter(evaluated.objects[1]).map((value,index)=>value-sceneMeshCenter(evaluated.objects[0])[index]);
  const displayDelta=sceneMeshCenter(display.objects[1]).map((value,index)=>value-sceneMeshCenter(display.objects[0])[index]);
  assert.deepEqual(displayDelta,[sourceDelta[0],sourceDelta[2],-sourceDelta[1]],"all occurrences share one rigid display mapping");
  assert.deepEqual(sceneTools.sceneForDisplayUp(evaluated,"y"),evaluated,"Y-up is the explicit identity default");
});

test("repeated quantities remain distinct selectable occurrences at their own placements", () => {
  const ids=["panel-01","panel-02","panel-03","panel-04","panel-05","panel-06","panel-07","panel-08","panel-09","panel-10","panel-11","panel-12","panel-13","panel-14","panel-15","panel-16"];
  const model = normaliseScene({ objects: ids.map((occurrence_id,index)=>({
    piece_id:"panel",occurrence_id,occurrence_index:index+1,
    dimensions_mm:{x:700,y:500,z:18},position_mm:{x:index*1000,y:0,z:0},
    orientation:{length_axis:"+x",width_axis:"+y",thickness_axis:"+z"},
  })) });

  assert.deepEqual(model.objects.map((item) => item.key), ids);
  assert.equal(new Set(model.objects.map((item)=>item.key)).size,16);
  assert.deepEqual([sceneMeshCenter(model.objects[0]),sceneMeshCenter(model.objects[15])],[[350,250,9],[15350,250,9]]);
  assert.ok(model.objects.every((item)=>item.pieceId==="panel"));
});

test("occurrence selection distinguishes the picked instance while retaining its component group", () => {
  assert.equal(typeof viewerTools.sceneSelectionKind, "function");
  const selected = { pieceId: "side", occurrenceKey: "side-left" };
  assert.equal(viewerTools.sceneSelectionKind({ pieceId: "side", key: "side-left" }, selected), "occurrence");
  assert.equal(viewerTools.sceneSelectionKind({ pieceId: "side", key: "side-right" }, selected), "component");
  assert.equal(viewerTools.sceneSelectionKind({ pieceId: "shelf", key: "shelf-1" }, selected), "none");
});

test("invalid or duplicate orthogonal transforms are rejected instead of rendered", () => {
  const model = normaliseScene({ objects: [
    { piece_id: "duplicate-axis", occurrence_id: "bad-1", dimensions_mm: { x: 10, y: 20, z: 3 }, position_mm: { x: 0, y: 0, z: 0 }, orientation: { length_axis: "+x", width_axis: "-x", thickness_axis: "+z" } },
    { piece_id: "reflection", occurrence_id: "bad-2", dimensions_mm: { x: 10, y: 20, z: 3 }, position_mm: { x: 0, y: 0, z: 0 }, orientation: { length_axis: "+x", width_axis: "+y", thickness_axis: "-z" } },
    { piece_id: "valid", occurrence_id: "same", dimensions_mm: { x: 10, y: 20, z: 3 }, position_mm: { x: 0, y: 0, z: 0 }, orientation: { length_axis: "+x", width_axis: "+y", thickness_axis: "+z" } },
    { piece_id: "valid", occurrence_id: "same", dimensions_mm: { x: 10, y: 20, z: 3 }, position_mm: { x: 30, y: 0, z: 0 }, orientation: { length_axis: "+x", width_axis: "+y", thickness_axis: "+z" } },
  ] });

  assert.deepEqual(model.objects.map((item) => item.key), ["same"]);
  assert.match(model.warnings.join(" "), /transformación ortogonal inválida/i);
  assert.match(model.warnings.join(" "), /identidad de ocurrencia duplicada/i);
});

test("legacy scenes retain identity orientation and bbox-min center semantics", () => {
  const item = normaliseScene({ objects: [{ piece_id: "legacy", dimensions_mm: { x: 40, y: 20, z: 5 }, position_mm: { x: 2, y: 3, z: 4 } }] }).objects[0];
  assert.equal(typeof sceneTools.sceneMeshTransform, "function");
  assert.deepEqual(sceneTools.sceneMeshTransform(item), {
    center: [22, 13, 6.5],
    rotationMatrix: [1, 0, 0, 0, 1, 0, 0, 0, 1],
  });
});

test("assembly phase presentation keeps accepted, rejected and incomplete outcomes explicit", () => {
  assert.equal(typeof sceneTools.presentGeneralAssembly, "function");
  const accepted = sceneTools.presentGeneralAssembly({ assembly_revision: 3, candidate: { alternative_id: "alt-right" }, report: { status: "accepted", placements: [{}, {}], issues: [] } });
  assert.equal(accepted.label, "Montaje validado · hipótesis");
  assert.match(accepted.detail, /2 instancias.*revisión 3/i);
  assert.match(accepted.detail, /alternativa alt-right/i);
  assert.equal(accepted.canRetry, false);

  const rejected = sceneTools.presentGeneralAssembly({ assembly_revision: 4, report: { status: "rejected", placements: [], issues: [{ code:"aabb_penetration",message: "World AABBs penetrate beyond collision tolerance.",occurrence_ids:["left","right"] }] } });
  assert.equal(rejected.label, "Montaje rechazado");
  assert.deepEqual(rejected.warnings, ["Interferencias entre piezas (1)"]);
  assert.equal(rejected.canRetry, true);

  const incomplete = sceneTools.presentGeneralAssembly({ assembly_revision: 5, report: { status: "incomplete", placements: [], issues: [] } });
  assert.equal(incomplete.label, "Montaje incompleto");
  assert.match(incomplete.detail, /sin colocaciones aceptadas/i);
  assert.equal(incomplete.canRetry, true);
});

test("assembly diagnostics are grouped and localized while retaining every raw issue", () => {
  assert.equal(typeof sceneTools.groupAssemblyIssues,"function");
  const issues=[
    ...Array.from({length:19},(_,index)=>({code:"aabb_penetration",message:"World AABBs penetrate beyond collision tolerance.",occurrence_ids:[`panel-${index}`,`panel-${index+1}`],source_refs:[]})),
    {code:"shared_evidence_identity",message:"Source geometry cannot identify two physical occurrences without explicit shared occlusion ambiguity.",occurrence_ids:["panel-1","panel-2"],source_refs:["entity:42"]},
    {code:"shared_evidence_identity",message:"Source geometry cannot identify two physical occurrences without explicit shared occlusion ambiguity.",occurrence_ids:["panel-3","panel-4"],source_refs:["entity:84"]},
    {code:"contour_box_fit_residual",message:"Non-rectangular contour cannot be treated as an exact panel box.",occurrence_ids:["panel-9"],source_refs:["contour:9"]},
  ];
  const groups=sceneTools.groupAssemblyIssues(issues);
  assert.deepEqual(groups.map(({code,label,count})=>({code,label,count})),[
    {code:"aabb_penetration",label:"Interferencias entre piezas",count:19},
    {code:"shared_evidence_identity",label:"Evidencia reutilizada entre piezas",count:2},
    {code:"contour_box_fit_residual",label:"Contornos no rectangulares",count:1},
  ]);
  assert.equal(groups[0].entries.length,19,"all raw diagnostics remain available in details");
  assert.equal(groups[0].occurrenceIds.length,20);
  assert.deepEqual(groups[1].sourceRefs,["entity:42","entity:84"]);
  assert.equal(groups[2].entries[0].message,"Non-rectangular contour cannot be treated as an exact panel box.");
});

test("assembly response preserves legacy attempts and every distinct accepted alternative", () => {
  assert.equal(typeof sceneTools.normaliseGeneralAssemblyResponse,"function");
  const legacy={assembly_revision:3,candidate:{alternative_id:"legacy"},report:{status:"accepted",placements:[],issues:[]}};
  const legacyBundle=sceneTools.normaliseGeneralAssemblyResponse(legacy);
  assert.equal(legacyBundle.current,legacy);
  assert.deepEqual(legacyBundle.acceptedAlternatives,[legacy]);
  assert.equal(legacyBundle.ambiguous,false);

  const current={assembly_revision:7,candidate:{alternative_id:"alt-a"},report:{status:"accepted",placements:[{}],issues:[]}};
  const other={assembly_revision:8,candidate:{alternative_id:"alt-b"},report:{status:"accepted",placements:[{}],issues:[]}};
  const bundle=sceneTools.normaliseGeneralAssemblyResponse({current,accepted_alternatives:[current,other],ambiguous:true});
  assert.equal(bundle.current,current);
  assert.deepEqual(bundle.acceptedAlternatives,[current,other]);
  assert.equal(bundle.ambiguous,true);
  const presentation=sceneTools.presentGeneralAssembly(bundle);
  assert.match(presentation.detail,/2 alternativas aceptadas/i);
  assert.match(presentation.warnings.join(" "),/ambigüedad.*sin resolver/i);
});

test("assembly state renders only the accepted current scene and never a rejected candidate", () => {
  assert.equal(typeof sceneTools.generalAssemblyScene,"function");
  const acceptedScene={status:"mounted_hypothesis",items:[]},fallback={status:"schematic_ready",items:[]};
  const accepted={current:{report:{status:"accepted",scene:acceptedScene}},accepted_alternatives:[],ambiguous:false};
  assert.equal(sceneTools.generalAssemblyScene(accepted,fallback),acceptedScene);
  const rejected={current:{report:{status:"rejected",scene:{status:"mounted_hypothesis",items:[{}]}}},accepted_alternatives:[{report:{status:"accepted",scene:acceptedScene}}],ambiguous:false};
  assert.equal(sceneTools.generalAssemblyScene(rejected,fallback),fallback);
});

test("rejected placements become a diagnostic scene only through the explicit helper", () => {
  assert.equal(typeof sceneTools.generalAssemblyDiagnosticScene,"function");
  const bomScene={status:"schematic_ready",items:[{component_id:"back",length:{value_mm:1200},width:{value_mm:800},thickness:{value_mm:8},occurrence_ids:[],scenario_occurrence_ids:["provisional:back-1"],occurrence_status:"provisional",status:"schematic_unplaced"}]};
  const rejected={current:{assembly_revision:8,candidate:{alternative_id:"rejected-8"},report:{status:"rejected",issues:[{code:"aabb_penetration",message:"World AABBs penetrate beyond collision tolerance.",occurrence_ids:["provisional:back-1","side-1"]}],placements:[{component_id:"back",occurrence_id:"provisional:back-1",occurrence_index:16,position_mm:{x:0,y:0,z:500},size_mm:{x:8,y:1200,z:800},orientation:{length_axis:"+y",width_axis:"+z",thickness_axis:"+x"},source_refs:["contour:back"]}]}}};

  assert.equal(sceneTools.generalAssemblyScene(rejected,bomScene),bomScene,"default rejected view remains schematic");
  const diagnostic=sceneTools.generalAssemblyDiagnosticScene(rejected,bomScene);
  assert.equal(diagnostic.diagnostic_rejected,true);
  assert.equal(diagnostic.status,"mounted_hypothesis");
  assert.equal(diagnostic.items[0].occurrence_id,"provisional:back-1");
  assert.equal(diagnostic.items[0].occurrence_index,16);
  assert.deepEqual(diagnostic.items[0].size_mm,{x:8,y:1200,z:800});
  assert.equal(diagnostic.items[0].occurrence_status,"provisional");
  assert.match(diagnostic.warnings.join(" "),/rechazado.*no validado.*solo inspección/i);
  const terminalIncomplete={current:{assembly_revision:9,candidate:{alternative_id:"last-rejected"},report:{...rejected.current.report,status:"incomplete",scene:null}}};
  assert.equal(sceneTools.generalAssemblyDiagnosticScene(terminalIncomplete,bomScene).items.length,1,"terminal incomplete retains explicit diagnostic placements without becoming accepted");
});

test("diagnostic scene abstains when rejected placements cannot be joined to BOM dimensions", () => {
  const rejected={current:{candidate:{alternative_id:"bad"},report:{status:"rejected",issues:[],placements:[{component_id:"missing",occurrence_id:"x",occurrence_index:1,position_mm:{x:0,y:0,z:0},size_mm:{x:1,y:2,z:3},orientation:{length_axis:"+x",width_axis:"+y",thickness_axis:"+z"}}]}}};
  assert.equal(sceneTools.generalAssemblyDiagnosticScene(rejected,{items:[]}),null);
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


test("general proposal remains inspectable in 3D without claiming review", () => {
  const scene = sceneTools.generalSceneForViewer({}, [{id:"side", dimensions:{length:{value:2400},width:{value:550},thickness:{value:18}}}]);
  assert.equal(scene.objects.length, 1);
  assert.equal(scene.objects[0].piece_id, "side");
  assert.match(scene.warnings[0], /provisional.*pendiente/);
  assert.equal(scene.collision_status, "not_applicable");
});
