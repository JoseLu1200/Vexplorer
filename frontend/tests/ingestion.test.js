import test from "node:test";
import assert from "node:assert/strict";

import { canStartDocumentAnalysis, presentDocumentIngestion } from "../core/ingestion.js";
import { generalRunOptions } from "../core/general.js";

test("PDF preview without scale is never presented as measured geometry", () => {
  const result = presentDocumentIngestion({
    source_name: "mueble.pdf", source_media_type: "application/pdf", source_size_bytes: 2048, status: "needs_review",
    source_unit: null, unit_scale_to_mm: null, scale_provenance: "unknown", warnings: ["unsupported_for_measurement"],
    pages: [{ page: 1, content_kind: "vector", preview_path: "/preview/1", normalized_dxf_path: null, warnings: ["scale_missing"] }],
  });
  assert.equal(result.format, "PDF");
  assert.equal(result.measurementReady, false);
  assert.match(result.summary, /revisión manual/i);
  assert.equal(result.pages[0].previewOnly, true);
});

test("converted DWG names its converter and normalized DXF provenance", () => {
  const result = presentDocumentIngestion({
    source_name: "recepcion.dwg", source_media_type: "application/acad", source_size_bytes: 4096,
    dxf_path: "/normalized/recepcion.dxf", dxf_sha256: "abc", converter: "ODA File Converter", warnings: [],
  });
  assert.equal(result.format, "DWG");
  assert.equal(result.measurementReady, true);
  assert.match(result.summary, /ODA File Converter/);
  assert.equal(result.normalizedDxfPath, "/normalized/recepcion.dxf");
});

test("actual PDF manifest keeps nested preview and page artifacts without claiming unknown-scale measurements", () => {
  const result = presentDocumentIngestion({
    document_id: "doc-parent",
    source: { filename: "drawing.pdf", media_type: "application/pdf", format: "pdf", size_bytes: 1234, sha256: "sha-parent", unit: "unknown" },
    ingestion: { state: "needs_review", capabilities: { page_geometry_analysis: true }, warnings: ["scale_missing"] },
    artifacts: {
      normalized_dxf: null,
      preview: { url: "/api/v1/documents/doc-parent/pages/1/preview.png", media_type: "image/png" },
      pages: [{ page_number: 1, content_kind: "vector", preview: { url: "/api/v1/documents/doc-parent/pages/1/preview.png" }, normalized_dxf: { url: "/api/v1/documents/doc-parent/pages/1/normalized.dxf", unit: "unknown" }, warnings: [] }],
    },
  });

  assert.equal(result.sha256, "sha-parent");
  assert.equal(result.status, "needs_review");
  assert.equal(result.previewUrl, "/api/v1/documents/doc-parent/pages/1/preview.png");
  assert.equal(result.pages[0].previewUrl, "/api/v1/documents/doc-parent/pages/1/preview.png");
  assert.equal(result.pages[0].normalizedDxfUrl, "/api/v1/documents/doc-parent/pages/1/normalized.dxf");
  assert.equal(result.pages[0].previewOnly, false);
  assert.equal(result.measurementReady, false);
});

test("scaled PDF child is measurement ready only when the immutable child publishes millimetres", () => {
  const result = presentDocumentIngestion({
    document_id: "doc-child",
    source: { filename: "drawing.pdf", format: "pdf", unit: "mm" },
    ingestion: { state: "ready", scale_provenance: { mm_per_pdf_point: 0.5, confirmed_by: "Técnica" } },
    artifacts: { preview: { url: "/preview.png" }, normalized_dxf: { url: "/normalized.dxf", unit: "mm" }, pages: [] },
  });

  assert.equal(result.measurementReady, true);
  assert.equal(result.normalizedDxfPath, "/normalized.dxf");
});

test("a selected raster PDF can start only the visual general live job without claiming measurements", () => {
  const ingestion=presentDocumentIngestion({
    document_id:"doc-child",source:{filename:"scan.pdf",format:"pdf",unit:"unknown"},
    ingestion:{state:"needs_review",warnings:["raster_or_unconverted_source_visual_review_only"]},
    artifacts:{preview:{url:"/api/v1/documents/doc-child/pages/1/preview.png"},normalized_dxf:null,pages:[]},
  });
  assert.equal(ingestion.measurementReady,false);
  assert.equal(canStartDocumentAnalysis(ingestion,{inputKind:"general_furniture",mode:"live"}),true);
  assert.equal(canStartDocumentAnalysis(ingestion,{inputKind:"mounted_orthographic_views",mode:"live"}),false);
  assert.deepEqual({document_id:"doc-child",mode:"live",input_kind:"general_furniture",...generalRunOptions("live")},{document_id:"doc-child",mode:"live",input_kind:"general_furniture",proposal_mode:"model_generated"});
});
