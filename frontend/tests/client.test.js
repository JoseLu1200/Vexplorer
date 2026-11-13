import test from "node:test";
import assert from "node:assert/strict";

import { ApiError, createApiClient } from "../api/client.js";

function response(status, body, headers = {}) {
  return new Response(body === null ? null : JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

test("the API client unwraps the canonical data envelope", async () => {
  const fetchImpl = async () => response(200, { schema_version: "0.2.0", data: { state: "needs_review" }, meta: {} });
  const client = createApiClient({ fetchImpl });

  assert.deepEqual(await client.getRun("run 1"), { state: "needs_review" });
});

test("the API client keeps a specific backend error for the interface", async () => {
  const fetchImpl = async () => response(409, {
    schema_version: "0.2.0",
    error: { code: "stale_result_revision", message: "La revisión ya cambió", details: {}, retryable: false },
    meta: {},
  });
  const client = createApiClient({ fetchImpl });

  await assert.rejects(client.getRun("run-1"), (error) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.code, "stale_result_revision");
    assert.equal(error.status, 409);
    return true;
  });
});

test("review requests send the base revision and an idempotency key", async () => {
  let request;
  const fetchImpl = async (url, init) => {
    request = { url, init };
    return response(201, { schema_version: "0.2.0", data: { result_revision: 2 }, meta: {} });
  };
  const client = createApiClient({ fetchImpl, idFactory: () => "review-key" });
  await client.review("run-1", { base_result_revision: 1, decisions: [] });

  assert.equal(request.url, "/api/v1/runs/run-1/reviews");
  assert.equal(request.init.headers["Idempotency-Key"], "review-key");
  assert.deepEqual(JSON.parse(request.init.body), { base_result_revision: 1, decisions: [] });
});

test("event history reads the persisted SSE snapshot as text", async () => {
  const fetchImpl = async () => new Response("id: 1\nevent: run_finished\ndata: {}\n\n", { status: 200, headers: { "content-type": "text/event-stream" } });
  const client = createApiClient({ fetchImpl });
  assert.equal(await client.getEventHistory("run-1"), "id: 1\nevent: run_finished\ndata: {}\n\n");
});

test("document drawing and preview stay available before a run", async () => {
  const urls = [];
  const fetchImpl = async (url) => { urls.push(url); return response(200, { data: { drawing_id: "d-1" } }); };
  const client = createApiClient({ fetchImpl });
  assert.deepEqual(await client.getDocumentDrawing("doc 1"), { drawing_id: "d-1" });
  assert.deepEqual(await client.getDocumentDrawing("doc 1", "separated_part_views"), { drawing_id: "d-1" });
  assert.equal(client.documentPreviewUrl("doc 1"), "/api/v1/documents/doc%201/preview.svg");
  assert.deepEqual(urls, ["/api/v1/documents/doc%201/drawing", "/api/v1/documents/doc%201/drawing?input_kind=separated_part_views"]);
});

test("0.3 endpoints preserve exact revision and similarity modes", async () => {
  const requests = [];
  const fetchImpl = async (url, init = {}) => { requests.push([url, init]); return response(200, { data: [] }); };
  const client = createApiClient({ fetchImpl, idFactory: () => "key" });
  await client.getRevisions("run-1");
  await client.getScene("run-1", 3);
  await client.getExplanations("run-1", 3);
  await client.findSimilar("run-1", { result_revision: 3, mode: "geometric", limit: 5 });
  assert.equal(requests[0][0], "/api/v1/runs/run-1/revisions");
  assert.equal(requests[1][0], "/api/v1/runs/run-1/scene?result_revision=3");
  assert.equal(requests[2][0], "/api/v1/runs/run-1/explanations?result_revision=3");
  assert.deepEqual(JSON.parse(requests[3][1].body), { result_revision: 3, mode: "geometric", limit: 5 });
});

test("parts-only run is explicit and parts convenience endpoint is revisioned by run", async () => {
  const requests = [];
  const fetchImpl = async (url, init = {}) => { requests.push([url, init]); return response(200, { data: {} }); };
  const client = createApiClient({ fetchImpl, idFactory: () => "key" });
  await client.createRun("doc-1", "geometry_only", "separated_part_views");
  await client.getParts("run parts");
  await client.getParts("run parts", 2);
  assert.deepEqual(JSON.parse(requests[0][1].body), { document_id: "doc-1", mode: "geometry_only", input_kind: "separated_part_views" });
  assert.equal(requests[1][0], "/api/v1/runs/run%20parts/parts");
  assert.equal(requests[2][0], "/api/v1/runs/run%20parts/parts?result_revision=2");
});
