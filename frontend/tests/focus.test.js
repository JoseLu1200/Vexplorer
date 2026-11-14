import test from "node:test";
import assert from "node:assert/strict";

import { nextFocusTarget } from "../core/focus.js";

test("drawer focus wraps in both keyboard directions", () => {
  const items = ["close", "first", "last"];
  assert.equal(nextFocusTarget(items, "last", false), "close");
  assert.equal(nextFocusTarget(items, "close", true), "last");
  assert.equal(nextFocusTarget(items, "first", false), "last");
});
