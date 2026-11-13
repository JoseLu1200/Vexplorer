import test from "node:test";
import assert from "node:assert/strict";

import { createEventLedger } from "../core/events.js";

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
