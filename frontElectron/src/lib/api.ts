import type { BackendEventPayload } from '../types/memoframe';

export class RpcError extends Error {
  code: string;
  hint: string;

  constructor(code: string, message: string, hint = '') {
    super(message);
    this.code = code;
    this.hint = hint;
  }
}

export async function rpc<T = unknown>(method: string, params: Record<string, unknown> = {}): Promise<T> {
  if (!window.memoframe || typeof window.memoframe.rpc !== 'function') {
    throw new RpcError('NO_BRIDGE', 'Electron IPC bridge is unavailable.');
  }
  const resp = await window.memoframe.rpc<T>(method, params);
  if (resp && resp.ok) return resp.result as T;
  const err = resp?.error || {};
  throw new RpcError(err.code || 'RPC_ERROR', err.message || 'Backend request failed', err.hint || '');
}

export function mediaUrl(filePath?: string | null): string {
  if (!filePath) return '';
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
  // If Electron preload has registered openFile, try that first
  if (typeof window.memoframe?.openFile === 'function') {
    try {
      const ok = await window.memoframe.openFile(filePath);
      if (ok) return true;
    } catch {
      // Fall through to bridge RPC fallback
    }
  }

  // Fallback via Python backend bridge RPC (works without restarting Electron)
  try {
    const res = await rpc<{ ok?: boolean }>('system.open_file', { path: filePath });
    return Boolean(res?.ok);
  } catch {
    return false;
  }
}

export function onBackendEvent(callback: (payload: BackendEventPayload) => void): () => void {
  if (!window.memoframe?.onEvent) return () => {};
  return window.memoframe.onEvent(callback);
}
