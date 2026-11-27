import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { onBackendEvent, rpc, selectFolder } from "../lib/api";
import { flushErrorQueue } from "../lib/errorMonitor";
import { THEME_FAMILIES, THEME_MAP } from "../lib/themes";
import { basename } from "../lib/utils";
import type {
  AppPreferences,
  EngineConfig,
  NotificationHistoryItem,
  PhotoRecord,
  ScanState,
  SystemInitPayload,
  ToastItem,
  ToastKind,
  ViewKey,
} from "../types/memoframe";

export const DEFAULT_PREFS: Required<AppPreferences> = {
  theme: "Studio Graphite Dark",
  defaultView: "photos",
  timezone: "local",
  dateFormat: "iso",
  density: "comfortable",
  reducedMotion: false,
  compactSidebar: false,
  notifySuccess: true,
  notifyErrors: true,
  notifyBackground: true,
  defaultPageSize: 40,
  onboardingCompleted: false,
};

export interface ExportRequest {
  photoIds: number[];
  label?: string;
}

export interface AppContextValue {
  activeView: ViewKey;
  setActiveView: (view: ViewKey) => void;
  theme: string;
  applyTheme: (name: string, persist?: boolean) => void;
  toggleLightDark: () => void;
  prefs: Required<AppPreferences>;
  updatePref: <K extends keyof AppPreferences>(key: K, value: AppPreferences[K]) => Promise<void>;
  resetPrefs: () => Promise<void>;
  connected: boolean;
  initReady: boolean;
  hasIndexedPhotos: boolean;
  inOnboarding: boolean;
  completeOnboarding: () => Promise<void>;
  modelGateOpen: boolean;
  completeModelGate: () => Promise<void>;
  reconnecting: boolean;
  backendError: string;
  workspace: string;
  config: EngineConfig;
  setConfig: React.Dispatch<React.SetStateAction<EngineConfig>>;
  initBackend: () => Promise<void>;
  dataVersion: number;
  invalidate: () => void;
  unresolvedErrors: number;
  refreshErrorCount: () => void;
  selectedPersonId: number | null;
  setSelectedPersonId: (id: number | null) => void;
  galleryExtraFilters: Record<string, unknown>;
  setGalleryExtraFilters: React.Dispatch<React.SetStateAction<Record<string, unknown>>>;
  lightboxPhoto: PhotoRecord | null;
  setLightboxPhoto: (photo: PhotoRecord | null) => void;
  lightboxList: PhotoRecord[];
  setLightboxList: (photos: PhotoRecord[]) => void;
  toasts: ToastItem[];
  notificationHistory: NotificationHistoryItem[];
  clearNotificationHistory: () => void;
  notify: (message: string, kind?: ToastKind) => void;
  scan: ScanState;
  scanLogs: string[];
  startScanFolder: (explicitFolder?: string) => Promise<void>;
  togglePauseScan: () => Promise<void>;
  cancelScan: () => Promise<void>;
  openPersonInGallery: (personId: number) => void;
  openGroupInGallery: (groupId: number, groupName?: string) => void;
  exportRequest: ExportRequest | null;
  openExportModal: (photoIds: number[], label?: string) => void;
  closeExportModal: () => void;
  commandPaletteOpen: boolean;
  setCommandPaletteOpen: (open: boolean) => void;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [activeView, setActiveView] = useState<ViewKey>("photos");
  const [theme, setThemeState] = useState(DEFAULT_PREFS.theme);
  const [prefs, setPrefs] = useState<Required<AppPreferences>>(DEFAULT_PREFS);
  const [connected, setConnected] = useState(false);
  const [initReady, setInitReady] = useState(false);
  const [hasIndexedPhotos, setHasIndexedPhotos] = useState(false);
  const [inOnboarding, setInOnboarding] = useState(false);
  const [modelGateOpen, setModelGateOpen] = useState(false);
  const pendingScanFolderRef = useRef<string | null>(null);
  const [reconnecting, setReconnecting] = useState(false);
  const [backendError, setBackendError] = useState("");
  const [workspace, setWorkspace] = useState("");
  const [config, setConfig] = useState<EngineConfig>({
    tagging_enabled: false,
    store_embeddings: false,
    log_path: "",
  });
  const [dataVersion, setDataVersion] = useState(0);
  const [unresolvedErrors, setUnresolvedErrors] = useState(0);
  const [selectedPersonId, setSelectedPersonId] = useState<number | null>(null);
  const [galleryExtraFilters, setGalleryExtraFilters] = useState<Record<string, unknown>>({});
  const [lightboxPhoto, setLightboxPhoto] = useState<PhotoRecord | null>(null);
  const [lightboxList, setLightboxList] = useState<PhotoRecord[]>([]);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [notificationHistory, setNotificationHistory] = useState<NotificationHistoryItem[]>([]);
  const [scan, setScan] = useState<ScanState>({
    running: false,
    paused: false,
    percent: 0,
    label: "Ready",
  });
  const [scanLogs, setScanLogs] = useState<string[]>([]);
  const [exportRequest, setExportRequest] = useState<ExportRequest | null>(null);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const toastIdRef = useRef(1);
  const prefsRef = useRef(prefs);
  prefsRef.current = prefs;
  const appliedDefaultViewRef = useRef(false);

  const notify = useCallback((message: string, kind: ToastKind = "info") => {
    const id = toastIdRef.current++;
    const p = prefsRef.current;
    setNotificationHistory(prev => [
      { id, message, kind, timestamp: new Date().toISOString() },
      ...prev.slice(0, 49),
    ]);
    if (kind === "success" && !p.notifySuccess) return;
    if (kind === "error" && !p.notifyErrors) return;
    if (kind === "info" && !p.notifyBackground) return;

    setToasts(prev => [...prev.slice(-3), { id, message, kind }]);
    window.setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 3600);
  }, []);

  const clearNotificationHistory = useCallback(() => setNotificationHistory([]), []);
  const invalidate = useCallback(() => setDataVersion(v => v + 1), []);

  const applyVisualPrefs = useCallback((next: Required<AppPreferences>) => {
    document.documentElement.setAttribute("data-density", next.density);
    document.documentElement.setAttribute(
      "data-reduced-motion",
      next.reducedMotion ? "true" : "false"
    );
  }, []);

  const applyTheme = useCallback((name: string, persist = true) => {
    if (!THEME_MAP[name]) return;
    document.documentElement.setAttribute("data-theme", name);
    try {
      localStorage.setItem("memoframe_theme", name);
    } catch {
      // ignore storage errors
    }
    setThemeState(name);
    setPrefs(prev => ({ ...prev, theme: name }));
    if (persist) {
      rpc("prefs.set", { key: "theme", value: name }).catch(() => {});
    }
  }, []);

  const updatePref = useCallback(
    async <K extends keyof AppPreferences>(key: K, value: AppPreferences[K]) => {
      setPrefs(prev => {
        const next = { ...prev, [key]: value } as Required<AppPreferences>;
        applyVisualPrefs(next);
        return next;
      });
      await rpc("prefs.set", { key: String(key), value });
    },
    [applyVisualPrefs]
  );

  const resetPrefs = useCallback(async () => {
    setPrefs(DEFAULT_PREFS);
    applyVisualPrefs(DEFAULT_PREFS);
    applyTheme(DEFAULT_PREFS.theme, true);
    for (const [k, v] of Object.entries(DEFAULT_PREFS)) {
      if (k === "theme") continue;
      await rpc("prefs.set", { key: k, value: v }).catch(() => {});
    }
  }, [applyTheme, applyVisualPrefs]);

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

  const refreshErrorCount = useCallback(() => {
    rpc<{ unresolved_count?: number }>("analytics.errors", { range: "all" })
      .then(res => {
        if (typeof res?.unresolved_count === "number") {
          setUnresolvedErrors(res.unresolved_count);
        }
      })
      .catch(() => {});
  }, []);

  const initBackend = useCallback(async () => {
    try {
      const info = await rpc<SystemInitPayload>("system.init");
      setConnected(Boolean(info.connected));
      setReconnecting(false);
      setBackendError(info.backend_error || "");
      setWorkspace(info.workspace || "");
      if (info.config) setConfig(info.config);

      const mergedPrefs: Required<AppPreferences> = {
        ...DEFAULT_PREFS,
        ...(info.prefs || {}),
      };
      setPrefs(mergedPrefs);
      applyVisualPrefs(mergedPrefs);

      const savedTheme = typeof mergedPrefs.theme === "string" ? mergedPrefs.theme : "";
      if (savedTheme && THEME_MAP[savedTheme]) applyTheme(savedTheme, false);

      if (!appliedDefaultViewRef.current && mergedPrefs.defaultView) {
        appliedDefaultViewRef.current = true;
        setActiveView(mergedPrefs.defaultView);
      }

      if (info.config_warnings?.length) {
        notify(`Config warnings: ${info.config_warnings[0]}`, "error");
      }

      let indexed = false;
      if (info.connected) {
        try {
          const st = await rpc<{ total_images?: number }>("system.stats");
          indexed = Number(st?.total_images || 0) > 0;
        } catch {
          indexed = false;
        }
      }
      setHasIndexedPhotos(indexed);
      if (info.connected && !indexed && !mergedPrefs.onboardingCompleted) {
        setInOnboarding(true);
      } else {
        setInOnboarding(false);
      }

      void flushErrorQueue().then(() => refreshErrorCount());
    } catch (err) {
      setConnected(false);
      setBackendError(err instanceof Error ? err.message : String(err));
    } finally {
      setInitReady(true);
    }
  }, [applyTheme, applyVisualPrefs, notify, refreshErrorCount]);

  useEffect(() => {
    initBackend();
    return onBackendEvent(({ event, data }) => {
      if (event === "bridge.ready") {
        setReconnecting(false);
        void initBackend();
      }
      if (event === "bridge.exited") {
        const code = (data as Record<string, unknown>)?.code;
        const msg = `Backend bridge exited unexpectedly (code=${code ?? "unknown"}). Click Retry to reconnect.`;
        setConnected(false);
        setReconnecting(false);
        setBackendError(msg);
        setScan({ running: false, paused: false, percent: 0, label: "Disconnected" });
        notify(msg, "error");
      }
      if (event === "error.captured" || event === "recovery.attempted") {
        refreshErrorCount();
      }
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
        rpc<{ total_images?: number }>("system.stats").then(st => setHasIndexedPhotos(Number(st?.total_images || 0) > 0)).catch(() => {});
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
  }, [initBackend, invalidate, notify, refreshErrorCount]);

  const startScanFolder = useCallback(
    async (explicitFolder?: string) => {
      if (scan.running) {
        notify("A scan is already running.", "error");
        return;
      }
      const folder = typeof explicitFolder === "string" && explicitFolder.trim() ? explicitFolder : await selectFolder();
      if (!folder) return;

      // Always verify AI models before starting a scan; if missing, enter blocking model loop
      // and resume scanning this folder automatically once models verify.
      try {
        const ms = await rpc<{ ready?: boolean }>("models.status");
        if (!ms?.ready) {
          pendingScanFolderRef.current = folder;
          setModelGateOpen(true);
          notify("Downloading required AI models before scanning...", "info");
          return;
        }
      } catch {
        // Proceed and let backend validate
      }

      try {
        await rpc("scan.start", { folder });
        setScanLogs([]);
        setScan({
          running: true,
          paused: false,
          percent: 0,
          label: `Scanning ${basename(folder)}...`,
        });
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        if (msg.toLowerCase().includes("models")) {
          pendingScanFolderRef.current = folder;
          setModelGateOpen(true);
        }
        setScan({ running: false, paused: false, percent: 0, label: "Ready" });
        notify(msg, "error");
      }
    },
    [scan.running, notify]
  );

  const completeOnboarding = useCallback(async () => {
    setInOnboarding(false);
    try {
      await updatePref("onboardingCompleted", true);
    } catch {
      // ignore
    }
  }, [updatePref]);

  const completeModelGate = useCallback(async () => {
    setModelGateOpen(false);
    const queued = pendingScanFolderRef.current;
    pendingScanFolderRef.current = null;
    if (queued) {
      await startScanFolder(queued);
    }
  }, [startScanFolder]);

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

  const openExportModal = useCallback((photoIds: number[], label?: string) => {
    if (!photoIds.length) return;
    setExportRequest({ photoIds, label });
  }, []);

  const closeExportModal = useCallback(() => setExportRequest(null), []);

  const value = useMemo<AppContextValue>(
    () => ({
      activeView,
      setActiveView,
      theme,
      applyTheme,
      toggleLightDark,
      prefs,
      updatePref,
      resetPrefs,
      connected,
      initReady,
      hasIndexedPhotos,
      inOnboarding,
      completeOnboarding,
      modelGateOpen,
      completeModelGate,
      reconnecting,
      backendError,
      workspace,
      config,
      setConfig,
      initBackend,
      dataVersion,
      invalidate,
      unresolvedErrors,
      refreshErrorCount,
      selectedPersonId,
      setSelectedPersonId,
      galleryExtraFilters,
      setGalleryExtraFilters,
      lightboxPhoto,
      setLightboxPhoto,
      lightboxList,
      setLightboxList,
      toasts,
      notificationHistory,
      clearNotificationHistory,
      notify,
      scan,
      scanLogs,
      startScanFolder,
      togglePauseScan,
      cancelScan,
      openPersonInGallery,
      openGroupInGallery,
      exportRequest,
      openExportModal,
      closeExportModal,
      commandPaletteOpen,
      setCommandPaletteOpen,
    }),
    [
      activeView,
      theme,
      applyTheme,
      toggleLightDark,
      prefs,
      updatePref,
      resetPrefs,
      connected,
      initReady,
      hasIndexedPhotos,
      inOnboarding,
      completeOnboarding,
      modelGateOpen,
      completeModelGate,
      reconnecting,
      backendError,
      workspace,
      config,
      initBackend,
      dataVersion,
      invalidate,
      unresolvedErrors,
      refreshErrorCount,
      selectedPersonId,
      galleryExtraFilters,
      lightboxPhoto,
      lightboxList,
      toasts,
      notificationHistory,
      clearNotificationHistory,
      notify,
      scan,
      scanLogs,
      startScanFolder,
      togglePauseScan,
      cancelScan,
      openPersonInGallery,
      openGroupInGallery,
      exportRequest,
      openExportModal,
      closeExportModal,
      commandPaletteOpen,
    ]
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used inside AppProvider");
  return ctx;
}
