/**
 * Persistencia del espacio de trabajo en IndexedDB, con todo acceso dentro de try/catch.
 * Si el navegador bloquea o vacía el almacenamiento (ventana privada, vista previa, cuota), la app sigue
 * funcionando en memoria durante la sesión y `persistent` queda en false.
 */
import type { WorkspaceData } from "./types";

const DB_NAME = "vexplorer-workspace";
const DB_VERSION = 1;
const OPEN_TIMEOUT_MS = 1500;

export interface WorkspaceDb {
  persistent: boolean;
  load(): Promise<WorkspaceData | null>;
  save(data: WorkspaceData): Promise<void>;
  getFile(planId: string): Promise<Blob | null>;
  putFile(planId: string, file: Blob): Promise<void>;
  deleteFile(planId: string): Promise<void>;
}

function memoryDb(): WorkspaceDb {
  let data: WorkspaceData | null = null;
  const files = new Map<string, Blob>();
  return {
    persistent: false,
    async load() { return data ? structuredClone(data) : null; },
    async save(next) { data = structuredClone(next); },
    async getFile(id) { return files.get(id) ?? null; },
    async putFile(id, file) { files.set(id, file); },
    async deleteFile(id) { files.delete(id); },
  };
}

function promisify<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function openIdb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("IndexedDB no responde")), OPEN_TIMEOUT_MS);
    let request: IDBOpenDBRequest;
    try {
      request = indexedDB.open(DB_NAME, DB_VERSION);
    } catch (error) {
      clearTimeout(timer);
      reject(error);
      return;
    }
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains("kv")) db.createObjectStore("kv");
      if (!db.objectStoreNames.contains("files")) db.createObjectStore("files");
    };
    request.onsuccess = () => { clearTimeout(timer); resolve(request.result); };
    request.onerror = () => { clearTimeout(timer); reject(request.error); };
    request.onblocked = () => { clearTimeout(timer); reject(new Error("IndexedDB bloqueada")); };
  });
}

/** Abre IndexedDB; si falla, devuelve un almacén en memoria. Los archivos que no se puedan escribir se quedan en memoria. */
export async function openWorkspaceDb(): Promise<WorkspaceDb> {
  let db: IDBDatabase;
  try {
    if (typeof indexedDB === "undefined") return memoryDb();
    db = await openIdb();
  } catch {
    return memoryDb();
  }
  const fallback = memoryDb();
  const tx = (store: "kv" | "files", mode: IDBTransactionMode) => db.transaction(store, mode).objectStore(store);
  const result: WorkspaceDb = {
    persistent: true,
    async load() {
      try {
        const value = await promisify(tx("kv", "readonly").get("workspace"));
        return (value as WorkspaceData | undefined) ?? null;
      } catch {
        result.persistent = false;
        return fallback.load();
      }
    },
    async save(data) {
      try {
        await promisify(tx("kv", "readwrite").put(data, "workspace"));
      } catch {
        result.persistent = false;
        await fallback.save(data);
      }
    },
    async getFile(id) {
      try {
        const value = await promisify(tx("files", "readonly").get(id));
        if (value instanceof Blob) return value;
      } catch { /* se intenta en memoria */ }
      return fallback.getFile(id);
    },
    async putFile(id, file) {
      try {
        await promisify(tx("files", "readwrite").put(file, id));
      } catch {
        await fallback.putFile(id, file);
      }
    },
    async deleteFile(id) {
      try { await promisify(tx("files", "readwrite").delete(id)); } catch { /* nada que borrar */ }
      await fallback.deleteFile(id);
    },
  };
  return result;
}
