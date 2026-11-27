import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { onBackendEvent, rpc, selectFolder } from "../lib/api";
import { THEME_FAMILIES, THEME_MAP } from "../lib/themes";
import { basename } from "../lib/utils";
import type {
  EngineConfig,
  PhotoRecord,
  ScanState,
  SystemInitPayload,
  ToastItem,
  ToastKind,
  ViewKey,
} from "../types/memoframe";

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
  lightboxList: PhotoRecord[];
  setLightboxList: (photos: PhotoRecord[]) => void;
  toasts: ToastItem[];
  notify: (message: string, kind?: ToastKind) => void;
  scan: ScanState;
  scanLogs: string[];
  startScanFolder: () => Promise<void>;
  togglePauseScan: () => Promise<void>;
  cancelScan: () => Promise<void>;
  openPersonInGallery: (personId: number) => void;
  openGroupInGallery: (groupId: number, groupName?: string) => void;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [activeView, setActiveView] = useState<ViewKey>("photos");
  const [theme, setThemeState] = useState("Nordic Slate Dark");
  const [connected, setConnected] = useState(false);
  const [backendError, setBackendError] = useState("");
  const [workspace, setWorkspace] = useState("");
  const [config, setConfig] = useState<EngineConfig>({
    tagging_enabled: false,
    store_embeddings: false,
    log_path: "",
  });
  const [dataVersion, setDataVersion] = useState(0);
  const [selectedPersonId, setSelectedPersonId] = useState<number | null>(null);
  const [galleryExtraFilters, setGalleryExtraFilters] = useState<Record<string, unknown>>({});
  const [lightboxPhoto, setLightboxPhoto] = useState<PhotoRecord | null>(null);
  const [lightboxList, setLightboxList] = useState<PhotoRecord[]>([]);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [scan, setScan] = useState<ScanState>({
    running: false,
    paused: false,
    percent: 0,
    label: "Ready",
  });
  const [scanLogs, setScanLogs] = useState<string[]>([]);
  const toastIdRef = useRef(1);

  const notify = useCallback((message: string, kind: ToastKind = "info") => {
    const id = toastIdRef.current++;
    setToasts(prev => [...prev.slice(-3), { id, message, kind }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 3600);
  }, []);

  const invalidate = useCallback(() => setDataVersion(v => v + 1), []);

  const applyTheme = useCallback((name: string, persist = true) => {
    if (!THEME_MAP[name]) return;
    document.documentElement.setAttribute("data-theme", name);
    try {
      localStorage.setItem("memoframe_theme", name);
    } catch {
      // ignore storage errors
    }
    setThemeState(name);
    if (persist) {
      rpc("prefs.set", { key: "theme", value: name }).catch(() => {});
    }
  }, []);

  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === "memoframe_theme" && e.newValue) {
        applyTheme(e.newValue, false);
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [applyTheme]);

  const toggleLightDark = useCallback(() => {
    const currentMeta = THEME_MAP[theme];
    const isDark = currentMeta?.isDark ?? true;
    const family =
      THEME_FAMILIES.find(f => f.darkTheme === theme || f.lightTheme === theme) ||
      THEME_FAMILIES[0];

    const targetTheme = isDark ? family.lightTheme : family.darkTheme;
    applyTheme(targetTheme, true);
  }, [theme, applyTheme]);

  const initBackend = useCallback(async () => {
    try {
      const info = await rpc<SystemInitPayload>("system.init");
      setConnected(Boolean(info.connected));
      setBackendError(info.backend_error || "");
      setWorkspace(info.workspace || "");
      if (info.config) setConfig(info.config);
      const savedTheme = typeof info.prefs?.theme === "string" ? info.prefs.theme : "";
      if (savedTheme && THEME_MAP[savedTheme]) applyTheme(savedTheme, false);
      if (info.config_warnings?.length) {
        notify(`Config warnings: ${info.config_warnings[0]}`, "error");
      }
    } catch (err) {
      setConnected(false);
      setBackendError(err instanceof Error ? err.message : String(err));
    }
  }, [applyTheme, notify]);

  useEffect(() => {
    initBackend();
    return onBackendEvent(({ event, data }) => {
      if (event === "bridge.ready") initBackend();
      if (event === "scan.progress") {
        const payloadData = (data || {}) as Record<string, unknown>;
        const pct = Number(payloadData.percent || 0);
        const label = String(payloadData.label || "Scanning...");
        setScan(s => ({
          ...s,
          running: true,
          percent: pct,
          label,
          stage: String(payloadData.stage || ""),
          done: Number(payloadData.done || 0),
          total: Number(payloadData.total || 0),
        }));
        setScanLogs(prev => [...prev.slice(-199), `[${pct}%] ${label}`]);
      }
      if (event === "scan.finished") {
        setScan({ running: false, paused: false, percent: 100, label: "Scan completed." });
        invalidate();
        notify("Finished scanning and organizing photos.", "success");
      }
      if (event === "scan.error") {
        const msg = String(data.message || "Unknown error");
        setScanLogs(prev => [...prev.slice(-199), `[ERROR] ${msg}`]);
        setScan({ running: false, paused: false, percent: 0, label: `Scan failed: ${msg}` });
        notify(`Scan failed: ${msg}`, "error");
      }
    });
  }, [initBackend, invalidate, notify]);

  const startScanFolder = useCallback(async () => {
    if (scan.running) {
      notify("A scan is already running.", "error");
      return;
    }
    const folder = await selectFolder();
    if (!folder) return;
    try {
      setScan({
        running: true,
        paused: false,
        percent: 0,
        label: `Scanning ${basename(folder)}...`,
      });
      await rpc("scan.start", { folder });
    } catch (err) {
      setScan({ running: false, paused: false, percent: 0, label: "Ready" });
      notify(err instanceof Error ? err.message : String(err), "error");
    }
  }, [scan.running, notify]);

  const togglePauseScan = useCallback(async () => {
    try {
      if (scan.paused) {
        await rpc("scan.resume");
        setScan(s => ({ ...s, paused: false, label: "Resuming..." }));
      } else {
        await rpc("scan.pause");
        setScan(s => ({ ...s, paused: true, label: "Paused" }));
      }
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "error");
    }
  }, [scan.paused, notify]);

  const cancelScan = useCallback(async () => {
    try {
      await rpc("scan.cancel");
      setScan(s => ({ ...s, label: "Cancelling scan..." }));
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "error");
    }
  }, [notify]);

  const openPersonInGallery = useCallback((personId: number) => {
    setSelectedPersonId(personId);
    setActiveView("photos");
  }, []);

  const openGroupInGallery = useCallback((groupId: number, groupName = "") => {
    setGalleryExtraFilters({ group_id: groupId, _group_label: groupName || `Event #${groupId}` });
    setActiveView("photos");
  }, []);

  const value = useMemo<AppContextValue>(
    () => ({
      activeView,
      setActiveView,
      theme,
      applyTheme,
      toggleLightDark,
      connected,
      backendError,
      workspace,
      config,
      setConfig,
      initBackend,
      dataVersion,
      invalidate,
      selectedPersonId,
      setSelectedPersonId,
      galleryExtraFilters,
      setGalleryExtraFilters,
      lightboxPhoto,
      setLightboxPhoto,
      lightboxList,
      setLightboxList,
      toasts,
      notify,
      scan,
      scanLogs,
      startScanFolder,
      togglePauseScan,
      cancelScan,
      openPersonInGallery,
      openGroupInGallery,
    }),
    [
      activeView,
      theme,
      applyTheme,
      toggleLightDark,
      connected,
      backendError,
      workspace,
      config,
      initBackend,
      dataVersion,
      invalidate,
      selectedPersonId,
      galleryExtraFilters,
      lightboxPhoto,
      lightboxList,
      toasts,
      notify,
      scan,
      scanLogs,
      startScanFolder,
      togglePauseScan,
      cancelScan,
      openPersonInGallery,
      openGroupInGallery,
    ]
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used inside AppProvider");
  return ctx;
}
