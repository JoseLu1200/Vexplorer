import test from "node:test";
import assert from "node:assert/strict";

import {
  DEFAULT_NEAR_DUPLICATE_THRESHOLD,
  evaluateDuplicatePrecedent,
  formatDuplicatePrecedentBanner,
} from "../core/duplicate_alert.js";

test("DEFAULT_NEAR_DUPLICATE_THRESHOLD defaults to 0.97", () => {
  assert.equal(DEFAULT_NEAR_DUPLICATE_THRESHOLD, 0.97);
});

test("evaluateDuplicatePrecedent abstains on null, undefined, or empty matches", () => {
  assert.deepEqual(evaluateDuplicatePrecedent(null), { found: false, match: null });
  assert.deepEqual(evaluateDuplicatePrecedent(undefined), { found: false, match: null });
  assert.deepEqual(evaluateDuplicatePrecedent([]), { found: false, match: null });
  assert.deepEqual(evaluateDuplicatePrecedent([{ score: 0.99 }]), { found: false, match: null });
  assert.deepEqual(evaluateDuplicatePrecedent([{ run_id: "run-1", score: Number.NaN }]), {
    found: false,
    match: null,
  });
});

test("evaluateDuplicatePrecedent abstains when top match is below threshold", () => {
  const result = evaluateDuplicatePrecedent([
    { run_id: "run-a", result_revision: 2, label: "Mesa roble", score: 0.969 },
    { run_id: "run-b", result_revision: 1, label: "Mesa pino", score: 0.85 },
  ]);

  assert.deepEqual(result, { found: false, match: null });
});

test("evaluateDuplicatePrecedent detects match at or above threshold and encodes run_id", () => {
  const match = {
    run_id: "run/special 42",
    result_revision: 3,
    label: "Estantería modular 1800",
    score: 0.99,
  };
  const result = evaluateDuplicatePrecedent([
    { run_id: "run-low", score: 0.8 },
    match,
  ]);

  assert.equal(result.found, true);
  assert.equal(result.match, match);
  assert.equal(result.score, 0.99);
  assert.equal(result.runId, "run/special 42");
  assert.equal(result.resultRevision, 3);
  assert.equal(result.label, "Estantería modular 1800");
  assert.equal(result.url, "?run=run%2Fspecial%2042");

  const exactThreshold = evaluateDuplicatePrecedent([{ run_id: "run-eq", score: 0.97 }]);
  assert.equal(exactThreshold.found, true);
  assert.equal(exactThreshold.runId, "run-eq");
  assert.equal(exactThreshold.resultRevision, null);
  assert.equal(exactThreshold.label, "run-eq");
});

test("evaluateDuplicatePrecedent respects custom threshold", () => {
  const matches = [{ run_id: "run-1", score: 0.92, label: "Armario" }];
  assert.equal(evaluateDuplicatePrecedent(matches).found, false);
  assert.equal(evaluateDuplicatePrecedent(matches, { threshold: 0.9 }).found, true);
});

test("formatDuplicatePrecedentBanner formats Spanish copy and link metadata", () => {
  const hidden = formatDuplicatePrecedentBanner({ found: false, match: null });
  assert.equal(hidden.visible, false);
  assert.equal(hidden.message, "");
  assert.equal(hidden.linkUrl, "");

  const evaluation = evaluateDuplicatePrecedent([
    {
      run_id: "run-prev-9",
      result_revision: 4,
      label: "Mesa comedor 200x100",
      score: 0.99,
    },
  ]);
  const formatted = formatDuplicatePrecedentBanner(evaluation);

  assert.equal(formatted.visible, true);
  assert.equal(formatted.title, "¿Ya hemos fabricado algo así?");
  assert.equal(
    formatted.message,
    "¿Ya hemos fabricado algo así? Coincidencia muy alta (similitud 0.99)",
  );
  assert.equal(formatted.linkText, "Abrir Mesa comedor 200x100 (rev. 4)");
  assert.equal(formatted.linkUrl, "?run=run-prev-9");
  assert.equal(formatted.scoreText, "0.99");
});
