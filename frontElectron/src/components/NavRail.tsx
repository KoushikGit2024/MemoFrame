import { useEffect, useRef, useState } from "react";
import type { LucideIcon } from "lucide-react";
import {
  Check,
  Clock,
  Copy,
  Images,
  Layers,
  Moon,
  Palette,
  PanelLeftClose,
  Settings,
  Sun,
  Users,
} from "lucide-react";
import { useApp } from "../context/AppContext";
import { THEME_FAMILIES, THEME_MAP } from "../lib/themes";
import type { ViewKey } from "../types/memoframe";

const NAV_ITEMS: ReadonlyArray<{ key: ViewKey; label: string; icon: LucideIcon }> = [
  { key: "photos", label: "Photos", icon: Images },
  { key: "people", label: "People", icon: Users },
  { key: "duplicates", label: "Duplicates", icon: Copy },
  { key: "bursts", label: "Bursts", icon: Layers },
  { key: "timeline", label: "Timeline", icon: Clock },
  { key: "settings", label: "Settings", icon: Settings },
];

export default function NavRail() {
  const { activeView, setActiveView, theme, applyTheme, toggleLightDark } = useApp();
  const [compact, setCompact] = useState<boolean>(() => window.innerWidth < 1000);
  const [manualToggle, setManualToggle] = useState(false);
  const [paletteMenuOpen, setPaletteMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const onResize = () => {
      if (!manualToggle) setCompact(window.innerWidth < 1000);
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [manualToggle]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setPaletteMenuOpen(false);
      }
    };
    if (paletteMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [paletteMenuOpen]);

  const isDark = THEME_MAP[theme]?.isDark ?? true;

  const getActiveStyle = (key: ViewKey) => {
    switch (key) {
      case "photos":
        return "bg-accent-secondary-light text-accent-secondary border-accent-secondary/30 border-l-2 border-l-accent-secondary";
      case "people":
        return "bg-violet-bg text-violet border-violet/30 border-l-2 border-l-violet";
      case "duplicates":
      case "bursts":
        return "bg-amber-bg text-amber border-amber/30 border-l-2 border-l-amber";
      case "timeline":
        return "bg-accent-light text-accent border-accent/30 border-l-2 border-l-accent";
      case "settings":
      default:
        return "bg-elevated text-primary border-hairline border-l-2 border-l-primary";
    }
  };

  const getInactiveIconHover = (key: ViewKey) => {
    switch (key) {
      case "photos":
        return "group-hover:text-accent-secondary";
      case "people":
        return "group-hover:text-violet";
      case "duplicates":
      case "bursts":
        return "group-hover:text-amber";
      case "timeline":
        return "group-hover:text-accent";
      default:
        return "group-hover:text-primary";
    }
  };

  return (
    <aside
      aria-label="Workspace Navigation"
      className={`shrink-0 bg-sidebar border-r border-subtle flex flex-col py-3.5 transition-all duration-150 ${
        compact ? "w-14 px-1.5 items-center" : "w-[216px] px-2.5"
      }`}
    >
      <div
        className={`flex items-center justify-between pb-3 mb-2 border-b border-subtle w-full ${compact ? "justify-center px-0" : "px-1.5"}`}
      >
        {!compact && (
          <div className="flex items-center gap-2 min-w-0">
            <img src="./logo.svg" alt="MemoFrame" className="w-7 h-7 object-contain shrink-0" />
            <div className="min-w-0">
              <div className="text-xs font-bold tracking-[0.1em] text-primary leading-none">
                MEMOFRAME
              </div>
              <div className="text-[11px] text-secondary mt-0.5 truncate">
                Photo &amp; Face Studio
              </div>
            </div>
          </div>
        )}
        <button
          type="button"
          title={compact ? "Expand sidebar" : "Collapse sidebar"}
          onClick={() => {
            setManualToggle(true);
            setCompact(c => !c);
          }}
          className="w-7 h-7 flex items-center justify-center rounded-md text-secondary hover:text-primary hover:bg-elevated transition-all duration-150 active:scale-95 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent-secondary cursor-pointer"
        >
          <PanelLeftClose
            className={`w-4 h-4 transition-transform duration-200 ${compact ? "rotate-180" : ""}`}
            strokeWidth={1.6}
          />
        </button>
      </div>

      {!compact && (
        <div className="text-[10px] font-semibold tracking-[0.08em] uppercase text-secondary px-2 pt-1 pb-1.5">
          Workspace
        </div>
      )}

      <nav className="relative flex flex-col gap-1 w-full">
        {(() => {
          const activeIndex = NAV_ITEMS.findIndex(item => item.key === activeView);
          if (activeIndex < 0) return null;
          return (
            <div
              aria-hidden="true"
              style={{ transform: `translateY(${activeIndex * 40}px)` }}
              className={`pointer-events-none absolute top-0 h-9 rounded-md border transition-all duration-200 ease-out ${
                compact ? "left-1/2 -translate-x-1/2 w-10" : "left-0 right-0"
              } ${getActiveStyle(activeView)}`}
            />
          );
        })()}
        {NAV_ITEMS.map(({ key, label, icon: Icon }) => {
          const active = activeView === key;
          return (
            <button
              key={key}
              type="button"
              aria-current={active ? "page" : undefined}
              title={compact ? label : undefined}
              onClick={() => setActiveView(key)}
              className={`relative z-10 group h-9 flex items-center rounded-md border border-transparent text-[13px] font-medium transition-all duration-150 active:scale-[0.98] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent-secondary disabled:opacity-45 disabled:cursor-not-allowed cursor-pointer ${
                compact ? "justify-center px-0 w-10 mx-auto" : "gap-2.5 px-2.5 w-full text-left"
              } ${
                active
                  ? "text-primary font-semibold"
                  : "bg-transparent text-secondary hover:bg-elevated/60 hover:text-primary"
              }`}
            >
              <Icon
                className={`w-4 h-4 shrink-0 transition-transform duration-150 group-hover:scale-105 ${active ? "" : getInactiveIconHover(key)}`}
                strokeWidth={active ? 1.8 : 1.6}
              />
              {!compact && <span className="truncate">{label}</span>}
            </button>
          );
        })}
      </nav>

      <div className="flex-1" />

      <div
        className="border-t border-subtle pt-2.5 w-full flex flex-col gap-1.5 relative"
        ref={menuRef}
      >
        {/* Hidden / Popover Theme Selection Palette Menu */}
        {paletteMenuOpen && (
          <div
            className={`absolute bottom-full mb-2 z-50 bg-card border border-hairline rounded-md p-3 shadow-2xl flex flex-col gap-2.5 ${
              compact ? "left-0 w-64" : "left-0 w-full"
            }`}
          >
            <div className="flex items-center justify-between border-b border-subtle pb-2">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-primary">
                <Palette className="w-3.5 h-3.5 text-accent" strokeWidth={1.8} />
                <span>Theme Palette</span>
              </div>
              <button
                type="button"
                onClick={toggleLightDark}
                title={isDark ? "Switch to Light Mode" : "Switch to Dark Mode"}
                className="h-6 px-2 rounded-xs border border-hairline bg-elevated text-[11px] font-medium text-primary flex items-center gap-1 hover:border-secondary transition-colors"
              >
                {isDark ? (
                  <>
                    <Sun className="w-3 h-3 text-amber" strokeWidth={1.8} />
                    <span>Light</span>
                  </>
                ) : (
                  <>
                    <Moon className="w-3 h-3 text-violet" strokeWidth={1.8} />
                    <span>Dark</span>
                  </>
                )}
              </button>
            </div>

            <div className="flex flex-col gap-1 max-h-56 overflow-y-auto pr-0.5">
              {THEME_FAMILIES.map(f => {
                const active = theme === f.darkTheme || theme === f.lightTheme;
                return (
                  <button
                    key={f.id}
                    type="button"
                    onClick={() => {
                      applyTheme(isDark ? f.darkTheme : f.lightTheme);
                      setPaletteMenuOpen(false);
                    }}
                    className={`h-8 px-2 rounded-xs border flex items-center justify-between text-xs transition-colors ${
                      active
                        ? "bg-elevated border-accent text-primary font-semibold"
                        : "bg-card border-transparent text-secondary hover:text-primary hover:bg-elevated/70"
                    }`}
                  >
                    <div className="flex items-center gap-2 truncate">
                      <span
                        className="w-3.5 h-3.5 rounded-full shrink-0 border border-hairline"
                        style={{
                          background: `conic-gradient(${f.previewAccent} 0deg 180deg, ${f.previewSecondary} 180deg 360deg)`,
                        }}
                      />
                      <span className="truncate">{f.label}</span>
                    </div>
                    {active && (
                      <Check className="w-3.5 h-3.5 text-accent shrink-0" strokeWidth={2} />
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Bottom Palette Trigger Button */}
        {compact ? (
          <button
            type="button"
            title="Change Theme Palette"
            onClick={() => setPaletteMenuOpen(o => !o)}
            className={`w-9 h-9 mx-auto flex items-center justify-center rounded-md border transition-all duration-150 active:scale-95 cursor-pointer ${
              paletteMenuOpen
                ? "border-accent bg-accent-light text-accent"
                : "border-subtle bg-card text-secondary hover:text-primary hover:border-hairline"
            }`}
          >
            <Palette className="w-4 h-4" strokeWidth={1.7} />
          </button>
        ) : (
          <button
            type="button"
            onClick={() => setPaletteMenuOpen(o => !o)}
            className={`w-full h-8 px-2.5 rounded-md border text-xs font-medium flex items-center justify-between transition-all duration-150 active:scale-[0.98] cursor-pointer ${
              paletteMenuOpen
                ? "border-accent bg-accent-light text-primary"
                : "border-subtle bg-card text-secondary hover:text-primary hover:border-hairline"
            }`}
          >
            <div className="flex items-center gap-2 truncate">
              <Palette className="w-3.5 h-3.5 text-accent shrink-0" strokeWidth={1.8} />
              <span className="truncate text-primary">
                {theme.replace(" Dark", "").replace(" Light", "")}
              </span>
            </div>
            <span
              className="w-2.5 h-2.5 rounded-full shrink-0"
              style={{
                background: `conic-gradient(${
                  THEME_FAMILIES.find(f => theme.includes(f.label))?.previewAccent || "var(--accent)"
                } 0deg 180deg, ${
                  THEME_FAMILIES.find(f => theme.includes(f.label))?.previewSecondary || "var(--accent)"
                } 180deg 360deg)`,
              }}
            />
          </button>
        )}
      </div>
    </aside>
  );
}
