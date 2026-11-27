import { useEffect, useMemo, useRef, useState } from "react";
import {
  BarChart3,
  Clock,
  Command,
  Copy,
  Download,
  FolderSearch,
  Images,
  Layers,
  Loader2,
  Moon,
  Palette,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  Sun,
  Trash2,
  Users,
} from "lucide-react";
import { useApp } from "../context/AppContext";
import { rpc } from "../lib/api";
import { THEME_FAMILIES, THEME_MAP } from "../lib/themes";

interface PaletteAction {
  id: string;
  label: string;
  category: string;
  keywords: string;
  disabled?: boolean;
  icon: typeof Command;
  run: () => void | Promise<void>;
}

export default function CommandPalette() {
  const {
    commandPaletteOpen,
    setCommandPaletteOpen,
    setActiveView,
    hasIndexedPhotos,
    connected,
    startScanFolder,
    lightboxPhoto,
    openExportModal,
    toggleLightDark,
    theme,
    applyTheme,
    invalidate,
    notify,
  } = useApp();

  const [query, setQuery] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "p") {
        e.preventDefault();
        setCommandPaletteOpen(!commandPaletteOpen);
      } else if (e.key === "Escape" && commandPaletteOpen) {
        setCommandPaletteOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [commandPaletteOpen, setCommandPaletteOpen]);

  useEffect(() => {
    if (commandPaletteOpen) {
      setQuery("");
      window.setTimeout(() => inputRef.current?.focus(), 20);
    }
  }, [commandPaletteOpen]);

  const isDark = THEME_MAP[theme]?.isDark ?? true;

  const actions = useMemo<PaletteAction[]>(
    () => [
      {
        id: "scan-folder",
        label: "Scan Photo Folder...",
        category: "Actions",
        keywords: "import index add folder scan",
        disabled: !connected,
        icon: FolderSearch,
        run: () => {
          setCommandPaletteOpen(false);
          void startScanFolder();
        },
      },
      ...(lightboxPhoto
        ? [
            {
              id: "export-current",
              label: "Export Current Open Photo...",
              category: "Actions",
              keywords: "save copy download export jpeg webp png",
              icon: Download,
              run: () => {
                setCommandPaletteOpen(false);
                openExportModal([lightboxPhoto.id], "Current Photo");
              },
            },
          ]
        : []),
      {
        id: "refresh-library",
        label: "Refresh Library Data",
        category: "Actions",
        keywords: "reload sync refresh",
        icon: RefreshCw,
        run: () => {
          invalidate();
          notify("Library view refreshed.", "info");
          setCommandPaletteOpen(false);
        },
      },
      {
        id: "clear-cache",
        label: "Clear Thumbnail Cache",
        category: "Maintenance",
        keywords: "storage disk space clean cache",
        disabled: !connected,
        icon: Trash2,
        run: async () => {
          const res = await rpc<{ freed_mb?: number }>("system.clear_cache");
          notify(`Reclaimed ~${res.freed_mb || 0} MB of cache.`, "success");
          setCommandPaletteOpen(false);
        },
      },
      {
        id: "run-doctor",
        label: "Run System Health Doctor",
        category: "Maintenance",
        keywords: "health check diagnostics doctor",
        disabled: !connected,
        icon: ShieldCheck,
        run: async () => {
          const rep = await rpc<{ checks?: Array<{ status: string }> }>("system.doctor");
          const issues = (rep?.checks || []).filter(c => c.status !== "ok").length;
          notify(
            issues === 0 ? "System Doctor: all checks passed." : `System Doctor found ${issues} issue(s).`,
            issues === 0 ? "success" : "error"
          );
          setActiveView("settings");
          setCommandPaletteOpen(false);
        },
      },
      {
        id: "toggle-mode",
        label: isDark ? "Switch to Light Mode" : "Switch to Dark Mode",
        category: "Appearance",
        keywords: "theme dark light mode",
        icon: isDark ? Sun : Moon,
        run: () => {
          toggleLightDark();
          setCommandPaletteOpen(false);
        },
      },
      ...THEME_FAMILIES.map(f => ({
        id: `theme-${f.id}`,
        label: `Theme: ${f.label} (${f.tagline})`,
        category: "Appearance",
        keywords: `theme color palette ${f.label} ${f.tagline}`,
        icon: Palette,
        run: () => {
          applyTheme(isDark ? f.darkTheme : f.lightTheme);
          setCommandPaletteOpen(false);
        },
      })),
      {
        id: "nav-photos",
        label: "Go to Photos Gallery",
        category: "Navigation",
        keywords: "grid photos gallery",
        icon: Images,
        run: () => {
          setActiveView("photos");
          setCommandPaletteOpen(false);
        },
      },
      {
        id: "nav-people",
        label: "Go to People & Faces",
        category: "Navigation",
        keywords: "faces persons people",
        disabled: !hasIndexedPhotos,
        icon: Users,
        run: () => {
          setActiveView("people");
          setCommandPaletteOpen(false);
        },
      },
      {
        id: "nav-duplicates",
        label: "Go to Duplicates",
        category: "Navigation",
        keywords: "duplicates cleanup",
        disabled: !hasIndexedPhotos,
        icon: Copy,
        run: () => {
          setActiveView("duplicates");
          setCommandPaletteOpen(false);
        },
      },
      {
        id: "nav-bursts",
        label: "Go to Bursts",
        category: "Navigation",
        keywords: "burst sequences shots",
        disabled: !hasIndexedPhotos,
        icon: Layers,
        run: () => {
          setActiveView("bursts");
          setCommandPaletteOpen(false);
        },
      },
      {
        id: "nav-timeline",
        label: "Go to Timeline",
        category: "Navigation",
        keywords: "events dates timeline",
        disabled: !hasIndexedPhotos,
        icon: Clock,
        run: () => {
          setActiveView("timeline");
          setCommandPaletteOpen(false);
        },
      },
      {
        id: "nav-analytics",
        label: "Go to Analytics & Error Intelligence",
        category: "Navigation",
        keywords: "metrics charts errors recovery analytics",
        icon: BarChart3,
        run: () => {
          setActiveView("analytics");
          setCommandPaletteOpen(false);
        },
      },
      {
        id: "nav-settings",
        label: "Go to Settings",
        category: "Navigation",
        keywords: "preferences config settings",
        icon: Settings,
        run: () => {
          setActiveView("settings");
          setCommandPaletteOpen(false);
        },
      },
    ],
    [
      connected,
      lightboxPhoto,
      isDark,
      hasIndexedPhotos,
      startScanFolder,
      openExportModal,
      invalidate,
      notify,
      toggleLightDark,
      applyTheme,
      setActiveView,
      setCommandPaletteOpen,
    ]
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return actions;
    return actions.filter(
      a =>
        a.label.toLowerCase().includes(q) ||
        a.category.toLowerCase().includes(q) ||
        a.keywords.toLowerCase().includes(q)
    );
  }, [actions, query]);

  if (!commandPaletteOpen) return null;

  const execute = async (action: PaletteAction) => {
    if (action.disabled || busyId) return;
    setBusyId(action.id);
    try {
      await action.run();
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "error");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Quick Actions"
      onClick={e => {
        if (e.target === e.currentTarget) setCommandPaletteOpen(false);
      }}
      className="fixed inset-0 z-50 bg-black/65 flex items-start justify-center pt-[12vh] p-4 animate-fade-in"
    >
      <div className="w-full max-w-lg bg-card border border-hairline rounded-md shadow-2xl overflow-hidden flex flex-col animate-modal-in">
        <div className="flex items-center gap-2 px-3.5 py-2.5 border-b border-subtle bg-sidebar">
          <Search className="w-4 h-4 text-accent-secondary shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => {
              if (e.key === "Enter" && filtered.length > 0) {
                const firstEnabled = filtered.find(a => !a.disabled);
                if (firstEnabled) void execute(firstEnabled);
              }
            }}
            placeholder="Run any action, switch view, or change theme..."
            className="flex-1 bg-transparent text-xs text-primary placeholder:text-secondary focus:outline-none"
          />
          <span className="font-mono text-[10px] text-secondary px-1.5 py-0.5 rounded-xs bg-input border border-subtle">
            ESC
          </span>
        </div>

        <div className="max-h-80 overflow-y-auto py-1.5 flex flex-col">
          {filtered.length === 0 ? (
            <div className="py-8 text-center text-xs text-secondary">No matching actions.</div>
          ) : (
            filtered.map(action => {
              const Icon = action.icon;
              const isBusy = busyId === action.id;
              return (
                <button
                  key={action.id}
                  type="button"
                  disabled={action.disabled || Boolean(busyId)}
                  onClick={() => void execute(action)}
                  className="w-full px-3.5 py-2 flex items-center justify-between gap-2 text-left text-xs text-primary hover:bg-elevated disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors"
                >
                  <span className="inline-flex items-center gap-2.5 min-w-0">
                    {isBusy ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin text-accent-secondary shrink-0" />
                    ) : (
                      <Icon className="w-3.5 h-3.5 text-secondary shrink-0" strokeWidth={1.7} />
                    )}
                    <span className="truncate">{action.label}</span>
                  </span>
                  <span className="font-mono text-[10px] text-secondary shrink-0">
                    {action.category}
                  </span>
                </button>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
