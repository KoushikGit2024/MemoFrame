/// <reference types="vite/client" />

import type { BackendEventPayload, RpcResponse } from './types/memoframe';

export interface MemoFramePreloadApi {
  rpc: <T = unknown>(method: string, params?: Record<string, unknown>) => Promise<RpcResponse<T>>;
  selectFolder: () => Promise<string | null>;
  revealFile: (filePath: string) => Promise<boolean>;
  openFile: (filePath: string) => Promise<boolean>;
  onEvent: (callback: (payload: BackendEventPayload) => void) => () => void;
  platform: string;
}

declare global {
  interface Window {
    memoframe?: MemoFramePreloadApi;
  }
}
