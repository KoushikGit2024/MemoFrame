import { useEffect, useState } from 'react';
import type { LucideIcon } from 'lucide-react';
import {
  Clock,
  Copy,
  Images,
  Layers,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  Sun,
  Users,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import { THEME_FAMILIES, THEME_MAP } from '../lib/themes';
import type { ViewKey } from '../types/memoframe';

const NAV_ITEMS: ReadonlyArray<{ key: ViewKey; label: string; icon: LucideIcon }> = [
  { key: 'photos', label: 'Photos', icon: Images },
  { key: 'people', label: 'People', icon: Users },
  { key: 'duplicates', label: 'Duplicates', icon: Copy },
  { key: 'bursts', label: 'Bursts', icon: Layers },
  { key: 'timeline', label: 'Timeline', icon: Clock },
  { key: 'settings', label: 'Settings', icon: Settings },
];

export default function NavRail() {
  const { activeView, setActiveView, theme, applyTheme, toggleLightDark } = useApp();
  const [compact, setCompact] = useState<boolean>(() => window.innerWidth < 1000);
  const [manualToggle, setManualToggle] = useState(false);

  useEffect(() => {
    const onResize = () => {
      if (!manualToggle) setCompact(window.innerWidth < 1000);
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [manualToggle]);

  const isDark = THEME_MAP[theme]?.isDark ?? true;

  return (
    <aside
      aria-label="Workspace Navigation"
      className={`shrink-0 bg-sidebar border-r border-subtle flex flex-col py-3.5 transition-all duration-150 ${
        compact ? 'w-14 px-1.5 items-center' : 'w-[216px] px-2.5'
      }`}
    >
      <div className={`flex items-center justify-between pb-3 mb-2 border-b border-subtle w-full ${compact ? 'justify-center px-0' : 'px-1.5'}`}>
        {!compact && (
          <div className="flex items-center gap-2 min-w-0">
            <span className="w-2 h-2 bg-accent rounded-[1px] shrink-0" />
            <div className="min-w-0">
              <div className="text-xs font-bold tracking-[0.1em] text-primary leading-none">MEMOFRAME</div>
              <div className="text-[11px] text-secondary mt-0.5 truncate">Photo &amp; Face Studio</div>
            </div>
          </div>
        )}
        <button
          type="button"
          title={compact ? 'Expand sidebar' : 'Collapse sidebar'}
          onClick={() => { setManualToggle(true); setCompact((c) => !c); }}
          className="w-7 h-7 flex items-center justify-center rounded-sm text-secondary hover:text-primary hover:bg-elevated transition-colors"
        >
          {compact ? <PanelLeftOpen className="w-4 h-4" strokeWidth={1.6} /> : <PanelLeftClose className="w-4 h-4" strokeWidth={1.6} />}
        </button>
      </div>

      {!compact && (
        <div className="text-[10px] font-semibold tracking-[0.08em] uppercase text-secondary px-2 pt-1 pb-1.5">
          Workspace
        </div>
      )}

      <nav className="flex flex-col gap-1 w-full">
        {NAV_ITEMS.map(({ key, label, icon: Icon }) => {
          const active = activeView === key;
          return (
            <button
              key={key}
              type="button"
              title={compact ? label : undefined}
              onClick={() => setActiveView(key)}
              className={`h-9 flex items-center rounded-sm border text-[13px] font-medium transition-colors ${
                compact ? 'justify-center px-0 w-10 mx-auto' : 'gap-2.5 px-2.5 w-full text-left'
              } ${
                active
                  ? 'bg-accent-light text-primary border-hairline border-l-2 border-l-accent'
                  : 'bg-transparent text-secondary border-transparent hover:bg-elevated hover:text-primary'
              }`}
            >
              <Icon className="w-4 h-4 shrink-0" strokeWidth={1.6} />
              {!compact && <span className="truncate">{label}</span>}
            </button>
          );
        })}
      </nav>

      <div className="flex-1" />

      <div className="border-t border-subtle pt-2.5 w-full flex flex-col gap-2">
        {compact ? (
          <button
            type="button"
            title={isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
            onClick={toggleLightDark}
            className="w-9 h-9 mx-auto flex items-center justify-center rounded-sm border border-subtle bg-card text-secondary hover:text-primary hover:border-hairline"
          >
            {isDark ? <Sun className="w-4 h-4" strokeWidth={1.6} /> : <Moon className="w-4 h-4" strokeWidth={1.6} />}
          </button>
        ) : (
          <div className="bg-card border border-subtle rounded-sm p-2.5 flex flex-col gap-2">
            <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.08em] text-secondary">
              <span className="font-semibold">Theme</span>
              <span className="font-mono text-[10.5px] truncate max-w-[100px]">{theme.replace(' Dark', '').replace(' Light', '')}</span>
            </div>
            <button
              type="button"
              onClick={toggleLightDark}
              className="h-7 px-2 flex items-center justify-center gap-1.5 rounded-xs border border-hairline bg-elevated text-primary text-xs font-medium hover:border-secondary transition-colors"
            >
              {isDark ? <Sun className="w-3.5 h-3.5 text-amber-400" strokeWidth={1.6} /> : <Moon className="w-3.5 h-3.5 text-accent" strokeWidth={1.6} />}
              <span>{isDark ? 'Switch to Light' : 'Switch to Dark'}</span>
            </button>
            <div className="grid grid-cols-6 gap-1 pt-0.5">
              {THEME_FAMILIES.map((f) => {
                const isSelected = theme === f.darkTheme || theme === f.lightTheme;
                return (
                  <button
                    key={f.id}
                    type="button"
                    title={`${f.label} (${isDark ? 'Dark' : 'Light'})`}
                    onClick={() => applyTheme(isDark ? f.darkTheme : f.lightTheme)}
                    style={{ backgroundColor: f.previewAccent }}
                    className={`h-5 rounded-xs border transition-all ${
                      isSelected
                        ? 'border-accent ring-2 ring-accent ring-offset-1 ring-offset-card scale-105'
                        : 'border-hairline hover:scale-105 hover:border-secondary'
                    }`}
                  />
                );
              })}
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
