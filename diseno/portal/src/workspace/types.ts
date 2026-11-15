/**
 * Espacio de trabajo del cliente: carpetas y planos guardados en el navegador.
 * El backend no lista documentos ni análisis, así que esta capa recuerda qué documento y qué análisis
 * corresponde a cada plano y guarda el DXF subido para poder descargarlo o volver a analizarlo.
 */
import type { DrawingExtraction, InputKind, Point2D, Result, ReviewRequest, RunEvent, RunMode, RunSnapshot, UploadedDocument } from "../api/types";

export type PlanStatus = "analyzing" | "needs_review" | "reviewed" | "error";

export interface Folder {
  id: string;
  name: string;
  parentId: string | null;
  createdAt: string;
}

/** Contorno reducido para la miniatura: solo puntos y si está cerrado. */
export interface ThumbContour { id: string; points: Point2D[]; closed: boolean }

export interface PlanRecord {
  id: string;
  /** Nombre visible; empieza siendo el nombre del archivo y se puede cambiar. */
  name: string;
  filename: string;
  folderId: string | null;
  createdAt: string;
  updatedAt: string;
  status: PlanStatus;
  /** Revisión vigente según la última respuesta del servidor. */
  revision: number | null;
  mode: RunMode;
  inputKind: InputKind | "general_furniture" | "mounted_orthographic_views";
  /**
   * Subidas por la mesa de trabajo (source "general"): mesa con plantilla de catálogo, mueble general nuevo o mueble
   * general cuyo DXF coincide por SHA-256 con una ejecución guardada (`casoGuardado`).
   */
  flujo?: "mesa" | "general" | "guardado";
  casoGuardado?: string;
  documentId: string | null;
  runId: string | null;
  /**
   * upload: archivo arrastrado, guardado en IndexedDB.
   * sample: DXF de ejemplo empaquetado con la app.
   * library: análisis que ya existe en la biblioteca del servidor (solo se siembra en modo de ejemplo).
   * server: análisis ya procesado en el servidor real (siembra anterior, se sustituye por «caso»).
   * caso: mueble de la carpeta «Muebles procesados» (src/casos); `asset` es el id del caso.
   * general: DXF subido por la vía de muebles generales; se abre con abrirRun y su `runId`.
   */
  source: "upload" | "sample" | "library" | "server" | "caso" | "general";
  /** Nombre del DXF empaquetado (sample y library). */
  asset?: string;
  libraryItemId?: string;
  sizeBytes: number;
  thumb: ThumbContour[] | null;
  error: { message: string; code: string } | null;
  /** Peticiones de revisión enviadas, en orden, para rehacer el análisis si el servidor ya no lo tiene. */
  reviews: ReviewRequest[];
}

export interface WorkspaceData {
  version: 1;
  folders: Folder[];
  plans: PlanRecord[];
  seeded: boolean;
}

export type LiveStage = "queued" | "uploading" | "reading" | "running" | "tracing" | "done" | "error";

/** Estado en memoria de un análisis en curso o recién terminado. */
export interface LiveAnalysis {
  planId: string;
  stage: LiveStage;
  /** user: el usuario lo ha arrastrado; sync: se rehace porque el servidor ya no lo tiene; seed: siembra inicial. */
  origin: "user" | "sync" | "seed";
  document: UploadedDocument | null;
  run: RunSnapshot | null;
  result: Result | null;
  drawing: DrawingExtraction | null;
  events: RunEvent[];
  error: { message: string; code: string; status: number; retryable: boolean } | null;
  startedAt: number;
}

/** Lo que necesita la pantalla de un plano abierto. */
export interface RunSnapshotBundle {
  planId: string;
  document: UploadedDocument | null;
  run: RunSnapshot;
  revisions: Result[];
  drawing: DrawingExtraction;
}

