/**
 * Frontend Error Intelligence & Self-Monitoring Fallback Queue.
 *
 * Captures unhandled exceptions, promise rejections, React boundary failures,
 * and RPC errors. If the backend reporting RPC is unavailable, events are
 * persisted in a bounded localStorage queue (max 100 items) and flushed with
 * exponential backoff + jitter once connectivity returns.
 */

const QUEUE_KEY = "memoframe_error_fallback_queue_v1";
const MAX_QUEUE_SIZE = 100;

export interface FrontendErrorReport {
  origin: "frontend";
  category: string;
  module: string;
  message: string;
  severity: "critical" | "error" | "warning" | "info";
  code?: string;
  stack_trace?: string;
  correlation_id?: string;
  context?: Record<string, unknown>;
  queued_at_utc?: string;
}

export interface ErrorMonitorHealth {
  installed: boolean;
  queuedCount: number;
  droppedCount: number;
  lastFlushAt: string | null;
  lastFlushOk: boolean;
}

let installed = false;
let droppedCount = 0;
let lastFlushAt: string | null = null;
let lastFlushOk = true;
let flushing = false;
let retryTimer: number | null = null;
let backoffAttempt = 0;

export function createCorrelationId(): string {
  const rand = Math.random().toString(36).slice(2, 8);
  return `mf-${Date.now().toString(36)}-${rand}`;
}

function readQueue(): FrontendErrorReport[] {
  try {
    const raw = localStorage.getItem(QUEUE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeQueue(items: FrontendErrorReport[]): void {
  try {
    localStorage.setItem(QUEUE_KEY, JSON.stringify(items.slice(-MAX_QUEUE_SIZE)));
  } catch {
    // Storage quota exceeded — drop oldest half and retry once
    try {
      localStorage.setItem(QUEUE_KEY, JSON.stringify(items.slice(-Math.floor(MAX_QUEUE_SIZE / 2))));
    } catch {
      // Ignore if storage is completely unavailable
    }
  }
}

function enqueue(item: FrontendErrorReport): void {
  const queue = readQueue();
  if (queue.length >= MAX_QUEUE_SIZE) {
    queue.shift();
    droppedCount += 1;
  }
  queue.push({ ...item, queued_at_utc: new Date().toISOString() });
  writeQueue(queue);
}

async function sendDirect(item: FrontendErrorReport): Promise<boolean> {
  if (!window.memoframe || typeof window.memoframe.rpc !== "function") {
    return false;
  }
  try {
    const resp = await window.memoframe.rpc("errors.report", {
      origin: item.origin,
      category: item.category,
      module: item.module,
      message: item.message,
      severity: item.severity,
      code: item.code || "",
      stack_trace: item.stack_trace || "",
      correlation_id: item.correlation_id || createCorrelationId(),
      context: {
        ...(item.context || {}),
        queued_at_utc: item.queued_at_utc,
      },
    });
    return Boolean(resp && resp.ok);
  } catch {
    return false;
  }
}

function scheduleFlushRetry(): void {
  if (retryTimer !== null) return;
  const baseMs = Math.min(30000, 1000 * Math.pow(2, backoffAttempt));
  const jitter = Math.floor(Math.random() * 400);
  backoffAttempt = Math.min(backoffAttempt + 1, 5);
  retryTimer = window.setTimeout(() => {
    retryTimer = null;
    void flushErrorQueue();
  }, baseMs + jitter);
}

export async function flushErrorQueue(): Promise<number> {
  if (flushing) return 0;
  const queue = readQueue();
  if (queue.length === 0) {
    backoffAttempt = 0;
    return 0;
  }
  flushing = true;
  let flushed = 0;
  const remaining: FrontendErrorReport[] = [];
  try {
    for (let i = 0; i < queue.length; i++) {
      const ok = await sendDirect(queue[i]);
      if (ok) {
        flushed += 1;
      } else {
        remaining.push(...queue.slice(i));
        break;
      }
    }
    writeQueue(remaining);
    lastFlushAt = new Date().toISOString();
    lastFlushOk = remaining.length === 0;
    if (remaining.length > 0) {
      scheduleFlushRetry();
    } else {
      backoffAttempt = 0;
    }
  } finally {
    flushing = false;
  }
  return flushed;
}

export function captureFrontendError(report: Omit<FrontendErrorReport, "origin">): void {
  const full: FrontendErrorReport = {
    origin: "frontend",
    ...report,
    correlation_id: report.correlation_id || createCorrelationId(),
  };
  void sendDirect(full).then(ok => {
    if (!ok) {
      enqueue(full);
      lastFlushOk = false;
      scheduleFlushRetry();
    }
  });
}

export function getErrorMonitorHealth(): ErrorMonitorHealth {
  return {
    installed,
    queuedCount: readQueue().length,
    droppedCount,
    lastFlushAt,
    lastFlushOk,
  };
}

export function installGlobalErrorHandlers(): () => void {
  if (installed) return () => {};
  installed = true;

  const onError = (event: ErrorEvent) => {
    captureFrontendError({
      category: "unhandled_exception",
      module: event.filename || "window",
      message: event.message || "Unhandled JavaScript error",
      severity: "error",
      stack_trace: event.error?.stack || `${event.filename}:${event.lineno}:${event.colno}`,
      context: { lineno: event.lineno, colno: event.colno },
    });
  };

  const onRejection = (event: PromiseRejectionEvent) => {
    const reason = event.reason;
    const message =
      reason instanceof Error ? reason.message : String(reason || "Unhandled promise rejection");
    const stack = reason instanceof Error ? reason.stack || "" : "";
    captureFrontendError({
      category: "unhandled_rejection",
      module: "promise",
      message,
      severity: "error",
      stack_trace: stack,
    });
  };

  window.addEventListener("error", onError);
  window.addEventListener("unhandledrejection", onRejection);

  return () => {
    installed = false;
    window.removeEventListener("error", onError);
    window.removeEventListener("unhandledrejection", onRejection);
  };
}
