import type { BackendEventPayload } from "../types/memoframe";
import { captureFrontendError, createCorrelationId } from "./errorMonitor";

export class RpcError extends Error {
  code: string;
  hint: string;
  correlationId: string;

  constructor(code: string, message: string, hint = "", correlationId = "") {
    super(message);
    this.code = code;
    this.hint = hint;
    this.correlationId = correlationId;
  }
}

// Only strictly idempotent read RPCs are eligible for controlled auto-retry on transient bridge failures.
const IDEMPOTENT_READ_PREFIXES = [
  "system.init",
  "system.stats",
  "system.doctor",
  "system.audit_log",
  "analytics.",
  "errors.list",
  "errors.detail",
  "recoveries.list",
  "models.status",
  "photos.query",
  "photos.detail",
  "photos.similar",
  "photos.failed",
  "photos.decode",
  "persons.list",
  "persons.get",
  "faces.list",
  "faces.crop",
  "duplicates.list",
  "bursts.list",
  "bursts.frames",
  "timeline.groups",
  "dates.suspicious",
  "tags.list",
  "saved_searches.list",
];

function isIdempotentRead(method: string): boolean {
  return IDEMPOTENT_READ_PREFIXES.some(p => method === p || method.startsWith(p));
}

function isTransientError(code: string, message: string): boolean {
  const m = message.toLowerCase();
  return (
    code === "RPC_ERROR" &&
    (m.includes("timeout") || m.includes("not running") || m.includes("database is locked"))
  );
}

export async function rpc<T = unknown>(
  method: string,
  params: Record<string, unknown> = {}
): Promise<T> {
  if (!window.memoframe || typeof window.memoframe.rpc !== "function") {
    throw new RpcError("NO_BRIDGE", "Electron IPC bridge is unavailable.");
  }

  const correlationId = createCorrelationId();
  const payload = { ...params, _correlation_id: correlationId };
  const maxAttempts = isIdempotentRead(method) ? 3 : 1;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const resp = await window.memoframe.rpc<T>(method, payload);
    if (resp && resp.ok) return resp.result as T;

    const err = resp?.error || {};
    const code = err.code || "RPC_ERROR";
    const message = err.message || "Backend request failed";
    const hint = err.hint || "";

    if (attempt < maxAttempts && isTransientError(code, message)) {
      const delayMs = 250 * Math.pow(2, attempt - 1) + Math.floor(Math.random() * 120);
      await new Promise(resolve => window.setTimeout(resolve, delayMs));
      continue;
    }

    if (method !== "errors.report") {
      captureFrontendError({
        category: "rpc_failure",
        module: method,
        code,
        message,
        severity: code === "BACKEND_NOT_CONNECTED" ? "warning" : "error",
        correlation_id: correlationId,
        context: { method, attempt, maxAttempts },
      });
    }
    throw new RpcError(code, message, hint, correlationId);
  }

  throw new RpcError("RPC_ERROR", `Failed calling ${method}`, "", correlationId);
}

export function mediaUrl(filePath?: string | null): string {
  if (!filePath) return "";
  return `memoframe-media://local?path=${encodeURIComponent(String(filePath))}`;
}

export function selectFolder(): Promise<string | null> {
  if (!window.memoframe?.selectFolder) return Promise.resolve(null);
  return window.memoframe.selectFolder();
}

export function revealFile(filePath: string): Promise<boolean> {
  if (!window.memoframe?.revealFile) return Promise.resolve(false);
  return window.memoframe.revealFile(filePath);
}

export async function openFile(filePath: string): Promise<boolean> {
  if (typeof window.memoframe?.openFile === "function") {
    try {
      const ok = await window.memoframe.openFile(filePath);
      if (ok) return true;
    } catch {
      // Fall through to bridge RPC fallback
    }
  }

  try {
    const res = await rpc<{ ok?: boolean }>("system.open_file", { path: filePath });
    return Boolean(res?.ok);
  } catch {
    return false;
  }
}

export function onBackendEvent(callback: (payload: BackendEventPayload) => void): () => void {
  if (!window.memoframe?.onEvent) return () => {};
  return window.memoframe.onEvent(callback);
}
