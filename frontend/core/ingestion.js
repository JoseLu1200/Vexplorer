const list = (value) => Array.isArray(value) ? value : [];

function extension(name = "") {
  const match = String(name).match(/\.([a-z0-9]+)$/i);
  return match?.[1]?.toUpperCase() ?? "ARCHIVO";
}

export function presentDocumentIngestion(raw = {}) {
  const source=raw.source??raw, ingestion=raw.ingestion??raw, artifacts=raw.artifacts??raw;
  const format = String(source.format ?? extension(source.source_name ?? source.filename)).toUpperCase();
  const pages = list(artifacts.pages ?? raw.pages).map((page, index) => ({
    ...page,
    page: page.page ?? page.page_number ?? index + 1,
    previewUrl: page.preview?.url ?? page.preview_path ?? null,
    normalizedDxfUrl: page.normalized_dxf?.url ?? page.normalized_dxf_path ?? null,
    previewOnly: !(page.normalized_dxf?.url ?? page.normalized_dxf_path),
    warnings: list(page.warnings),
  }));
  const scaleKnown = source.unit === "mm" || (ingestion.unit_scale_to_mm != null && Number.isFinite(Number(ingestion.unit_scale_to_mm))) || (ingestion.scale_provenance?.mm_per_pdf_point != null && Number.isFinite(Number(ingestion.scale_provenance.mm_per_pdf_point)));
  const normalizedDxf=artifacts.normalized_dxf?.url??artifacts.normalized_dxf?.path??artifacts.normalized_dxf??raw.dxf_path;
  const converted = Boolean(normalizedDxf || pages.some((page) => page.normalizedDxfUrl));
  const measurementReady = format === "DXF" || (format === "DWG" && converted) || (format === "PDF" && Boolean(normalizedDxf) && scaleKnown);
  const warnings = list(ingestion.warnings ?? raw.warnings);
  let summary;
  if (format === "DWG" && converted) summary = `DWG convertido a DXF por ${ingestion.converter ?? raw.converter ?? "convertidor configurado"}`;
  else if (format === "PDF" && !measurementReady) summary = "PDF disponible para análisis visual automático; las medidas métricas permanecen desconocidas sin escala o evidencia métrica";
  else summary = `${format} ${measurementReady ? "disponible para lectura geométrica" : "pendiente de normalización"}`;
  return {
    format,
    name: source.source_name ?? source.filename ?? "Documento",
    mediaType: source.source_media_type ?? source.media_type ?? null,
    sizeBytes: source.source_size_bytes ?? source.size_bytes ?? null,
    sha256: source.source_sha256 ?? source.sha256 ?? raw.sha256 ?? null,
    status: ingestion.state ?? ingestion.status ?? raw.status ?? (measurementReady ? "ready" : "needs_review"),
    measurementReady,
    summary,
    warnings,
    pages,
    previewUrl: artifacts.preview?.url ?? artifacts.preview_path ?? null,
    normalizedDxfPath: normalizedDxf ?? null,
    converter: ingestion.converter ?? raw.converter ?? null,
    scaleProvenance: ingestion.scale_provenance ?? raw.scale_provenance ?? null,
  };
}

export function canStartDocumentAnalysis(ingestion, { inputKind, mode } = {}) {
  return Boolean(ingestion?.measurementReady || (inputKind === "general_furniture" && mode === "live" && ingestion?.previewUrl));
}
