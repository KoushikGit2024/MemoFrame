import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { onBackendEvent, rpc, selectFolder } from '../lib/api';
import { THEME_MAP } from '../lib/themes';
import { basename } from '../lib/utils';
import type {
  EngineConfig,
  PhotoRecord,
  ScanState,
  SystemInitPayload,
  ToastItem,
  ToastKind,
  ViewKey,
} from '../types/memoframe';

export interface AppContextValue {
  activeView: ViewKey;
  setActiveView: (view: ViewKey) => void;
  theme: string;
  applyTheme: (name: string, persist?: boolean) => void;
  toggleLightDark: () => void;
  connected: boolean;
  backendError: string;
  workspace: string;
  config: EngineConfig;
  setConfig: React.Dispatch<React.SetStateAction<EngineConfig>>;
  initBackend: () => Promise<void>;
  dataVersion: number;
  invalidate: () => void;
  selectedPersonId: number | null;
  setSelectedPersonId: (id: number | null) => void;
  galleryExtraFilters: Record<string, unknown>;
  setGalleryExtraFilters: React.Dispatch<React.SetStateAction<Record<string, unknown>>>;
  lightboxPhoto: PhotoRecord | null;
  setLightboxPhoto: (photo: PhotoRecord | null) => void;
  toasts: ToastItem[];
  notify: (message: string, kind?: ToastKind) => void;
  scan: ScanState;
  startScanFolder: () => Promise<void>;
  togglePauseScan: () => Promise<void>;
  cancelScan: () => Promise<void>;
  openPersonInGallery: (personId: number) => void;
  openGroupInGallery: (groupId: number, groupName?: string) => void;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [activeView, setActiveView] = useState<ViewKey>('photos');
  const [theme, setThemeState] = useState('Dark Slate');
  const [lastDarkTheme, setLastDarkTheme] = useState('Dark Slate');
  const [connected, setConnected] = useState(false);
  const [backendError, setBackendError] = useState('');
  const [workspace, setWorkspace] = useState('');
  const [config, setConfig] = useState<EngineConfig>({ tagging_enabled: false, store_embeddings: false, log_path: '' });
  const [dataVersion, setDataVersion] = useState(0);
  const [selectedPersonId, setSelectedPersonId] = useState<number | null>(null);
  const [galleryExtraFilters, setGalleryExtraFilters] = useState<Record<string, unknown>>({});
  const [lightboxPhoto, setLightboxPhoto] = useState<PhotoRecord | null>(null);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [scan, setScan] = useState<ScanState>({ running: false, paused: false, percent: 0, label: 'Ready' });
  const toastIdRef = useRef(1);

  const notify = useCallback((message: string, kind: ToastKind = 'info') => {
    const id = toastIdRef.current++;
    setToasts((prev) => [...prev.slice(-3), { id, message, kind }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 3600);
  }, []);

  const invalidate = useCallback(() => setDataVersion((v) => v + 1), []);

  const applyTheme = useCallback((name: string, persist = true) => {
    if (!THEME_MAP[name]) return;
    document.documentElement.setAttribute('data-theme', name);
    setThemeState(name);
    if (name !== 'Light Canvas') setLastDarkTheme(name);
    if (persist) {
      rpc('prefs.set', { key: 'theme', value: name }).catch(() => {});
      if (name !== 'Light Canvas') {
        rpc('prefs.set', { key: 'last_dark_theme', value: name }).catch(() => {});
      }
    }
  }, []);

  const toggleLightDark = useCallback(() => {
    applyTheme(theme === 'Light Canvas' ? (lastDarkTheme || 'Dark Slate') : 'Light Canvas', true);
  }, [theme, lastDarkTheme, applyTheme]);

  const initBackend = useCallback(async () => {
    try {
      const info = await rpc<SystemInitPayload>('system.init');
      setConnected(Boolean(info.connected));
      setBackendError(info.backend_error || '');
      setWorkspace(info.workspace || '');
      if (info.config) setConfig(info.config);
      const savedDark = typeof info.prefs?.last_dark_theme === 'string' ? info.prefs.last_dark_theme : '';
      if (savedDark && THEME_MAP[savedDark]) setLastDarkTheme(savedDark);
      const savedTheme = typeof info.prefs?.theme === 'string' ? info.prefs.theme : '';
      if (savedTheme && THEME_MAP[savedTheme]) applyTheme(savedTheme, false);
      if (info.config_warnings?.length) {
        notify(`Config warnings: ${info.config_warnings[0]}`, 'error');
      }
    } catch (err) {
      setConnected(false);
      setBackendError(err instanceof Error ? err.message : String(err));
    }
  }, [applyTheme, notify]);

  useEffect(() => {
    initBackend();
    return onBackendEvent(({ event, data }) => {
      if (event === 'bridge.ready') initBackend();
      if (event === 'scan.progress') {
        setScan((s) => ({
          ...s,
          running: true,
          percent: Number(data.percent || 0),
          label: String(data.label || 'Scanning...'),
        }));
      }
      if (event === 'scan.finished') {
        setScan({ running: false, paused: false, percent: 100, label: 'Scan completed.' });
        invalidate();
        notify('Finished scanning and organizing photos.', 'success');
      }
      if (event === 'scan.error') {
        const msg = String(data.message || 'Unknown error');
        setScan({ running: false, paused: false, percent: 0, label: `Scan failed: ${msg}` });
        notify(`Scan failed: ${msg}`, 'error');
      }
    });
  }, [initBackend, invalidate, notify]);

  const startScanFolder = useCallback(async () => {
    if (scan.running) {
      notify('A scan is already running.', 'error');
      return;
    }
    const folder = await selectFolder();
    if (!folder) return;
    try {
      setScan({ running: true, paused: false, percent: 0, label: `Scanning ${basename(folder)}...` });
      await rpc('scan.start', { folder });
    } catch (err) {
      setScan({ running: false, paused: false, percent: 0, label: 'Ready' });
      notify(err instanceof Error ? err.message : String(err), 'error');
    }
  }, [scan.running, notify]);

  const togglePauseScan = useCallback(async () => {
    try {
      if (scan.paused) {
        await rpc('scan.resume');
        setScan((s) => ({ ...s, paused: false, label: 'Resuming...' }));
      } else {
        await rpc('scan.pause');
        setScan((s) => ({ ...s, paused: true, label: 'Paused' }));
      }
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), 'error');
    }
  }, [scan.paused, notify]);

  const cancelScan = useCallback(async () => {
    try {
      await rpc('scan.cancel');
      setScan((s) => ({ ...s, label: 'Cancelling scan...' }));
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), 'error');
    }
  }, [notify]);

  const openPersonInGallery = useCallback((personId: number) => {
    setSelectedPersonId(personId);
    setActiveView('photos');
  }, []);

  const openGroupInGallery = useCallback((groupId: number, groupName = '') => {
    setGalleryExtraFilters({ group_id: groupId, _group_label: groupName || `Event #${groupId}` });
    setActiveView('photos');
  }, []);

  const value: AppContextValue = {
    activeView, setActiveView,
    theme, applyTheme, toggleLightDark,
    connected, backendError, workspace, config, setConfig, initBackend,
    dataVersion, invalidate,
    selectedPersonId, setSelectedPersonId,
    galleryExtraFilters, setGalleryExtraFilters,
    lightboxPhoto, setLightboxPhoto,
    toasts, notify,
    scan, startScanFolder, togglePauseScan, cancelScan,
    openPersonInGallery, openGroupInGallery,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used inside AppProvider');
  return ctx;
}
