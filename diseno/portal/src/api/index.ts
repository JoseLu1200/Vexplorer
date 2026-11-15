import { createHttpClient, type VexplorerApi } from "./client";
import { createMockClient } from "./mock";

/** Único interruptor: VITE_USE_MOCK=true usa datos de ejemplo; cualquier otro valor, el backend real. */
export const USE_MOCK = String(import.meta.env.VITE_USE_MOCK ?? "true") === "true";

export const api: VexplorerApi = USE_MOCK ? createMockClient() : createHttpClient();
export { ApiError } from "./client";
export type { VexplorerApi } from "./client";

// Vía de muebles generales. Mismo origen que el cliente real; en modo mock la interfaz usa src/casos.
import { createGeneralClient } from "./general";
export const generalApi = createGeneralClient(String(import.meta.env.VITE_API_BASE ?? ""));
export { createGeneralClient, GeneralApiError, NEEDS_MODEL_MESSAGE, newIdempotencyKey, describeError } from "./general";
export type { GeneralApi, JobView, ReconstructionJob, GeneralConfigSummary } from "./general";
