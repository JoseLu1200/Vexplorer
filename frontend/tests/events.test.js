import test from "node:test";
import assert from "node:assert/strict";

import { createEventLedger, eventLabel, eventTimestamp, parseEventStream } from "../core/events.js";

test("duplicate events are ignored while event order is preserved", () => {
  const ledger = createEventLedger("run-1");
  ledger.append({ run_id: "run-1", sequence: 1, event_type: "run_state_changed", data: {} });
  ledger.append({ run_id: "run-1", sequence: 2, event_type: "tool_completed", data: {} });
  ledger.append({ run_id: "run-1", sequence: 2, event_type: "tool_completed", data: {} });
  ledger.append({ run_id: "run-1", sequence: 3, event_type: "run_finished", data: {} });
  assert.deepEqual(ledger.events().map((item) => item.sequence), [1, 2, 3]);
  assert.deepEqual(ledger.gaps(), []);
});

test("sequence gaps are recorded before advancing", () => {
  const ledger = createEventLedger("run-1");
  ledger.append({ run_id: "run-1", sequence: 1, event_type: "run_state_changed", data: {} });
  ledger.append({ run_id: "run-1", sequence: 3, event_type: "run_finished", data: {} });
  assert.deepEqual(ledger.gaps(), [{ after: 1, before: 3 }]);
});

test("persisted SSE history includes human review and estimate events after run finish", () => {
  const body = [
    "id: 3\nevent: run_finished\ndata: {\"schema_version\":\"0.2.0\",\"run_id\":\"run-1\",\"sequence\":3,\"event_type\":\"run_finished\",\"data\":{}}",
    "id: 4\nevent: human_review_committed\ndata: {\"schema_version\":\"0.2.0\",\"run_id\":\"run-1\",\"sequence\":4,\"event_type\":\"human_review_committed\",\"data\":{\"result_revision\":2}}",
    "id: 5\nevent: estimate_committed\ndata: {\"schema_version\":\"0.2.0\",\"run_id\":\"run-1\",\"sequence\":5,\"event_type\":\"estimate_committed\",\"data\":{\"total\":127.84}}",
  ].join("\n\n") + "\n\n";
  const events = parseEventStream(body);
  assert.deepEqual(events.map((item) => item.sequence), [3, 4, 5]);
  assert.equal(eventLabel(events[1]), "Revisión humana registrada");
  assert.equal(eventLabel(events[2]), "Estimación guardada");
});

test("event timestamp reads the canonical nested data field", () => {
  assert.equal(eventTimestamp({ data: { timestamp: "2026-11-13T22:45:00Z" } }), "2026-11-13T22:45:00Z");
});
