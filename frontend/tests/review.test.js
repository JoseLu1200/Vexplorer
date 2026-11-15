import test from "node:test";
import assert from "node:assert/strict";

import { buildReviewPayload, buildScenarioReviewPayload } from "../core/review.js";

test("review payload preserves base revision and excludes client reviewer identity", () => {
  const payload = buildReviewPayload({ result_revision: 3 }, [{ scenario_id: "scenario-a", decision: "accept", reason: "Montaje confirmado en taller" }]);
  assert.deepEqual(payload, {
    base_result_revision: 3,
    decisions: [{ scenario_id: "scenario-a", decision: "accept", reason: "Montaje confirmado en taller" }],
  });
  assert.equal("reviewer_id" in payload, false);
});

test("review decisions require a written reason", () => {
  assert.throws(() => buildReviewPayload({ result_revision: 1 }, [{ scenario_id: "a", decision: "accept", reason: " " }]), /motivo/i);
});

test("scenario review sends technical premises without calculating dimensions in the browser", () => {
  assert.deepEqual(buildScenarioReviewPayload({ result_revision: 2 }, {
    scenario_id: "between-sides",
    reviewer_name: "Marta Ruiz",
    confirmed_thickness_mm: "18",
    material: "Melamina blanca",
    finish: "Canto ABS",
    notes: "Montaje confirmado por el responsable de taller",
  }), {
    base_result_revision: 2,
    reviewer_name: "Marta Ruiz",
    scenario_id: "between-sides",
    confirmed_thickness_mm: 18,
    material: "Melamina blanca",
    finish: "Canto ABS",
    notes: "Montaje confirmado por el responsable de taller",
  });
});

test("scenario review rejects a missing or non positive thickness", () => {
  assert.throws(() => buildScenarioReviewPayload({ result_revision: 1 }, { scenario_id: "a", reviewer_name: "Marta", confirmed_thickness_mm: "0", notes: "motivo" }), /espesor/i);
});

test("review draft guard tracks effective changes and protects unload", async () => {
  const { createReviewDraftGuard } = await import("../core/review.js");
  const listeners=new Map(),windowListeners=new Map(),control={id:"review-reason",name:"",type:"text",value:"initial",checked:false,disabled:false,dataset:{}};
  const form={dataset:{},querySelectorAll:()=>[control],addEventListener:(type,handler)=>listeners.set(type,handler),removeEventListener(){}};
  const windowRef={addEventListener:(type,handler)=>windowListeners.set(type,handler),removeEventListener(){}};
  let confirms=0;
  const guard=createReviewDraftGuard(form,{windowRef,confirmDiscard:()=>{confirms+=1;return false;}});
  guard.markClean();
  assert.equal(form.dataset.dirty,"false");
  control.value="changed";listeners.get("input")();
  assert.equal(form.dataset.dirty,"true");
  assert.equal(guard.canDiscard(),false);assert.equal(confirms,1);
  let prevented=false;const event={preventDefault(){prevented=true;},returnValue:null};windowListeners.get("beforeunload")(event);
  assert.equal(prevented,true);assert.equal(event.returnValue,"");
  control.value="initial";listeners.get("input")();
  assert.equal(form.dataset.dirty,"false");
});
