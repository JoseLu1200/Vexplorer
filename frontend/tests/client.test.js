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

test("FastAPI detail errors remain actionable in the interface", async () => {
  const client=createApiClient({fetchImpl:async()=>response(422,{detail:"confirmed_value_requires_human_provenance"})});
  await assert.rejects(()=>client.reviewGeneralFurniture("run-1",{}),(error)=>error.status===422&&error.code==="confirmed_value_requires_human_provenance"&&error.message==="confirmed_value_requires_human_provenance");
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
  assert.throws(() => client.getParts("run parts"), /revisión/i);
  await client.getParts("run parts", 2);
  assert.deepEqual(JSON.parse(requests[0][1].body), { document_id: "doc-1", mode: "geometry_only", input_kind: "separated_part_views" });
  assert.equal(requests[1][0], "/api/v1/runs/run%20parts/parts?result_revision=2");
});

test("private session and durable jobs use their explicit API resources", async () => {
  const requests = [];
  const fetchImpl = async (url, init = {}) => {
    requests.push([url, init]);
    return response(url.endsWith("/jobs") ? 202 : 200, { data: { id: "job-1", state: "queued" } });
  };
  const client = createApiClient({ fetchImpl, idFactory: () => "job-key" });

  await client.getSession();
  await client.createJob({ document_id: "doc-1", mode: "geometry_only" });
  await client.getJob("job 1");

  assert.equal(requests[0][0], "/api/v1/session");
  assert.equal(requests[1][0], "/api/v1/jobs");
  assert.equal(requests[1][1].headers["Idempotency-Key"], "job-key");
  assert.deepEqual(JSON.parse(requests[1][1].body), { document_id: "doc-1", mode: "geometry_only" });
  assert.equal(requests[2][0], "/api/v1/jobs/job%201");
});

test("retrying a terminal job creates a linked durable execution without reupload",async()=>{
  const requests=[],client=createApiClient({fetchImpl:async(url,init={})=>{requests.push([url,init]);return response(202,{data:{id:"job-2",state:"queued",retry_of_job_id:"job-1"}});},idFactory:()=>"retry-key"});
  const result=await client.retryJob("job 1");
  assert.equal(result.retry_of_job_id,"job-1");
  assert.equal(requests[0][0],"/api/v1/jobs/job%201/retry");
  assert.equal(requests[0][1].method,"POST");
  assert.equal(requests[0][1].headers["Idempotency-Key"],"retry-key");
});

test("resuming a saved proposal uses the dedicated review-only endpoint",async()=>{
  const requests=[],client=createApiClient({fetchImpl:async(url,init={})=>{requests.push([url,init]);return response(202,{data:{id:"job-3",state:"queued",resume_of_job_id:"job-1"}});},idFactory:()=>"resume-key"});
  await client.resumeJob("job 1");
  assert.equal(requests[0][0],"/api/v1/jobs/job%201/resume");
  assert.equal(requests[0][1].method,"POST");
  assert.equal(requests[0][1].headers["Idempotency-Key"],"resume-key");
});

test("replay availability is checked with the exact server resolved run request", async () => {
  let request;
  const client = createApiClient({ fetchImpl: async (url, init) => { request = [url, init]; return response(200, { data: { available: true } }); } });
  const body = { document_id: "doc-1", mode: "recorded_replay", input_kind: "mounted_views_legacy" };
  assert.deepEqual(await client.getReplayAvailability(body), { available: true });
  assert.equal(request[0], "/api/v1/replay-availability");
  assert.deepEqual(JSON.parse(request[1].body), body);
});

test("a deployment base path prefixes API and generated artifact URLs without changing local routes", async () => {
  const requests = [];
  const client = createApiClient({ basePath: "/vexplorer/", fetchImpl: async (url) => { requests.push(url); return response(200, { data: {} }); } });
  await client.getSession();
  await client.getJob("job-1");
  assert.deepEqual(requests, ["/vexplorer/api/v1/session", "/vexplorer/api/v1/jobs/job-1"]);
  assert.equal(client.documentPreviewUrl("doc-1"), "/vexplorer/api/v1/documents/doc-1/preview.svg");
  assert.equal(client.resourceUrl("/api/v1/runs/run-1/file.svg"), "/vexplorer/api/v1/runs/run-1/file.svg");
  assert.equal(client.resourceUrl("https://files.invalid/file.svg"), "https://files.invalid/file.svg");
});

test("table runs and revisioned artifacts preserve the frozen 0.5 request fields", async () => {
  const requests = [];
  const fetchImpl = async (url, init = {}) => { requests.push([url, init]); return response(200, { data: {} }); };
  const client = createApiClient({ fetchImpl, idFactory: () => "key" });
  await client.createRun("doc-table", "geometry_only", "mounted_orthographic_views", {
    table_profile: "rectangular_table_v1",
    proposal_mode: "catalog_baseline",
    table_template_id: "side_supports_v1",
  });
  assert.throws(() => client.getTable("run table"), /revisión/i);
  await client.getTable("run table", 2);
  await client.generateTableDrawings("run table", { result_revision: 2 });
  await client.getTableDrawings("run table", 2);
  await client.generateTableCosts("run table", { result_revision: 2, scope: { edge_scope: "none" } });
  await client.getTableCosts("run table", 2);
  await client.getTableCostCatalog();

  assert.deepEqual(JSON.parse(requests[0][1].body), {
    document_id: "doc-table",
    mode: "geometry_only",
    input_kind: "mounted_orthographic_views",
    table_profile: "rectangular_table_v1",
    proposal_mode: "catalog_baseline",
    table_template_id: "side_supports_v1",
  });
  assert.equal(requests[1][0], "/api/v1/runs/run%20table/table?result_revision=2");
  assert.equal(requests[2][0], "/api/v1/runs/run%20table/table-drawings");
  assert.equal(requests[3][0], "/api/v1/runs/run%20table/table-drawings?result_revision=2");
  assert.equal(requests[4][0], "/api/v1/runs/run%20table/table-costs");
  assert.equal(requests[5][0], "/api/v1/runs/run%20table/table-costs?result_revision=2");
  assert.equal(requests[6][0], "/api/v1/table-cost-catalog");
  assert.equal(client.tableDrawingUrl("run table", "sheet/1", "svg", 2, "hash +1"), "/api/v1/runs/run%20table/table-drawings/sheet%2F1.svg?result_revision=2&program_hash=hash+%2B1");
});

test("general furniture endpoints keep proposal and review revisions explicit", async () => {
  const requests = [];
  const fetchImpl = async (url, init = {}) => { requests.push([url, init]); return response(200, { data: {} }); };
  const client = createApiClient({ fetchImpl, idFactory: () => "general-key" });

  await client.createGeneralProposal("run general", { mode: "live", base_proposal_revision: 0 });
  await client.getGeneralFurniture("run general");
  await client.reviewGeneralFurniture("run general", { base_proposal_revision: 2, operations: [] });
  await client.getGeneralDerived("run general", 3, 2);

  assert.equal(requests[0][0], "/api/v1/runs/run%20general/general/proposals");
  assert.deepEqual(JSON.parse(requests[0][1].body), { mode: "live", base_proposal_revision: 0 });
  assert.equal(requests[1][0], "/api/v1/runs/run%20general/general");
  assert.equal(requests[2][0], "/api/v1/runs/run%20general/general/reviews");
  assert.equal(requests[2][1].headers["Idempotency-Key"], "general-key");
  assert.deepEqual(JSON.parse(requests[2][1].body), { base_proposal_revision: 2, operations: [] });
  assert.equal(requests[3][0], "/api/v1/runs/run%20general/general/derived?proposal_revision=3&review_revision=2");
  assert.equal(client.generalArtifactUrl("run general","bom/1",3,2),"/api/v1/runs/run%20general/general/artifacts/bom%2F1?proposal_revision=3&review_revision=2");
});

test("general assembly reads exact revisions without spending and retries as a durable idempotent job", async () => {
  const requests = [];
  const fetchImpl = async (url, init = {}) => { requests.push([url, init]); return response(init.method === "POST" ? 202 : 200, { data: { id: "assembly-job", state: "queued" } }); };
  const client = createApiClient({ fetchImpl, idFactory: () => "assembly-retry-key" });

  await client.getGeneralAssembly("run assembly", 4, 2);
  await client.retryGeneralAssembly("run assembly", { base_proposal_revision: 4, base_review_revision: 2 });

  assert.equal(requests[0][0], "/api/v1/runs/run%20assembly/general/assembly?proposal_revision=4&review_revision=2");
  assert.equal(requests[0][1].method, undefined, "read-only assembly inspection remains a GET");
  assert.equal(requests[1][0], "/api/v1/runs/run%20assembly/general/assembly/retry");
  assert.equal(requests[1][1].method, "POST");
  assert.equal(requests[1][1].headers["Idempotency-Key"], "assembly-retry-key");
  assert.deepEqual(JSON.parse(requests[1][1].body), { base_proposal_revision: 4, base_review_revision: 2 });
});

test("general assembly cancellation targets the durable retry job without a request body", async () => {
  let request;
  const client=createApiClient({fetchImpl:async(url,init={})=>{request=[url,init];return response(202,{data:{job_id:"job/7",cancel_requested:true}});}});
  assert.deepEqual(await client.cancelGeneralAssembly("run assembly","job/7"),{job_id:"job/7",cancel_requested:true});
  assert.equal(request[0],"/api/v1/runs/run%20assembly/general/assembly/retry/job%2F7/cancel");
  assert.equal(request[1].method,"POST");
  assert.equal(request[1].body,undefined);
});

test("recent projects, executions and generic cancellation use durable resources", async () => {
  const requests=[];
  const client=createApiClient({fetchImpl:async(url,init={})=>{requests.push([url,init]);return response(200,{data:{items:[],next_cursor:null,state:"cancelled"}});}});
  await client.getProjects({limit:20,cursor:"next token"});
  await client.getExecutions({limit:10});
  await client.cancelJob("job/7");
  assert.equal(requests[0][0],"/api/v1/projects?limit=20&cursor=next+token");
  assert.equal(requests[1][0],"/api/v1/executions?limit=10");
  assert.equal(requests[2][0],"/api/v1/jobs/job%2F7/cancel");
  assert.equal(requests[2][1].method,"POST");
});

test("historical imports, records, comparables and estimates have visible client operations", async () => {
  const requests = [];
  const fetchImpl = async (url, init = {}) => { requests.push([url, init]); return response(200, { data: {} }); };
  const client = createApiClient({ fetchImpl, idFactory: () => "history-key" });
  const file = new Blob(["project,cost\nA,12"], { type: "text/csv" });

  await client.importHistory(file, { dryRun: false });
  await client.getHistory({ origin: "actual", limit: 25 });
  await client.getHistoricalComparables({ run_id: "run-1", result_revision: 2 });
  await client.estimateFromHistory({ run_id: "run-1", result_revision: 2 });
  await client.getHistoricalScenarios({ run_id:"run-1",proposal_revision:2,review_revision:1,retrieval_method:"attribute" });

  assert.equal(requests[0][0], "/api/v1/history/imports?dry_run=false");
  assert.equal(requests[0][1].method, "POST");
  assert.ok(requests[0][1].body instanceof FormData);
  assert.equal(requests[1][0], "/api/v1/history?origin=actual&limit=25");
  assert.equal(requests[2][0], "/api/v1/history/comparables");
  assert.equal(requests[3][0], "/api/v1/history/estimate");
  assert.equal(requests[4][0], "/api/v1/history/scenarios");
  assert.deepEqual(JSON.parse(requests[4][1].body),{run_id:"run-1",proposal_revision:2,review_revision:1,retrieval_method:"attribute"});
});

test("a PDF page normalization creates an immutable child document with explicit scale", async () => {
  let request;
  const client = createApiClient({ fetchImpl: async (url, init) => { request=[url,init]; return response(201,{data:{document_id:"child-1"}}); }, idFactory:()=>"pdf-key" });
  await client.normalizePdfPage("parent 1",2,{mm_per_pdf_point:0.3528,confirmed_by:"ana",reason:"Escala 1:1 confirmada en cajetín"});
  assert.equal(request[0],"/api/v1/documents/parent%201/pdf-pages/2/normalize");
  assert.equal(request[1].headers["Idempotency-Key"],"pdf-key");
  assert.deepEqual(JSON.parse(request[1].body),{mm_per_pdf_point:0.3528,confirmed_by:"ana",reason:"Escala 1:1 confirmada en cajetín"});
});
