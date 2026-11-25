import type { ThemeMeta } from '../types/memoframe';

export interface ThemeFamily {
  id: string;
  label: string;
  darkTheme: string;
  lightTheme: string;
  previewAccent: string;
  previewBgDark: string;
  previewBgLight: string;
}

export const THEME_FAMILIES: ThemeFamily[] = [
  {
    id: 'nordic',
    label: 'Nordic Slate',
    darkTheme: 'Nordic Slate Dark',
    lightTheme: 'Nordic Slate Light',
    previewAccent: '#38bdf8', // crisp arctic sky blue
    previewBgDark: '#0c131a',
    previewBgLight: '#f1f5f9',
  },
  {
    id: 'obsidian',
    label: 'Obsidian Rose',
    darkTheme: 'Obsidian Rose Dark',
    lightTheme: 'Obsidian Rose Light',
    previewAccent: '#fb7185', // radiant neon rose
    previewBgDark: '#120d13',
    previewBgLight: '#fff1f2',
  },
  {
    id: 'cyberpunk',
    label: 'Neon Cyberpunk',
    darkTheme: 'Neon Cyberpunk Dark',
    lightTheme: 'Neon Cyberpunk Light',
    previewAccent: '#22d3ee', // high-voltage electric cyan & violet
    previewBgDark: '#080811',
    previewBgLight: '#f0fdfa',
  },
  {
    id: 'forest',
    label: 'Alpine Emerald',
    darkTheme: 'Alpine Emerald Dark',
    lightTheme: 'Alpine Emerald Light',
    previewAccent: '#10b981', // vivid botanical emerald
    previewBgDark: '#07140e',
    previewBgLight: '#f0fdf4',
  },
  {
    id: 'solar',
    label: 'Solar Flare',
    darkTheme: 'Solar Flare Dark',
    lightTheme: 'Solar Flare Light',
    previewAccent: '#f59e0b', // warm vibrant golden amber
    previewBgDark: '#141008',
    previewBgLight: '#fffbeb',
  },
  {
    id: 'vapor',
    label: 'Vapor Wave',
    darkTheme: 'Vapor Wave Dark',
    lightTheme: 'Vapor Wave Light',
    previewAccent: '#ec4899', // retro magenta & purple glow
    previewBgDark: '#0d0b18',
    previewBgLight: '#fdf2f8',
  },
];

export const THEMES: ThemeMeta[] = [
  // 1. Nordic Slate
  { name: 'Nordic Slate Dark', isDark: true, bg: '#0c131a', card: '#131e29', accent: '#38bdf8' },
  { name: 'Nordic Slate Light', isDark: false, bg: '#f1f5f9', card: '#ffffff', accent: '#0284c7' },

  // 2. Obsidian Rose
  { name: 'Obsidian Rose Dark', isDark: true, bg: '#120d13', card: '#1d1520', accent: '#fb7185' },
  { name: 'Obsidian Rose Light', isDark: false, bg: '#fff1f2', card: '#ffffff', accent: '#e11d48' },

  // 3. Neon Cyberpunk
  { name: 'Neon Cyberpunk Dark', isDark: true, bg: '#080811', card: '#111124', accent: '#22d3ee' },
  { name: 'Neon Cyberpunk Light', isDark: false, bg: '#f0fdfa', card: '#ffffff', accent: '#0891b2' },

  // 4. Alpine Emerald
  { name: 'Alpine Emerald Dark', isDark: true, bg: '#07140e', card: '#0f241a', accent: '#10b981' },
  { name: 'Alpine Emerald Light', isDark: false, bg: '#f0fdf4', card: '#ffffff', accent: '#059669' },

  // 5. Solar Flare
  { name: 'Solar Flare Dark', isDark: true, bg: '#141008', card: '#211a0d', accent: '#f59e0b' },
  { name: 'Solar Flare Light', isDark: false, bg: '#fffbeb', card: '#ffffff', accent: '#d97706' },

  // 6. Vapor Wave
  { name: 'Vapor Wave Dark', isDark: true, bg: '#0d0b18', card: '#19152e', accent: '#ec4899' },
  { name: 'Vapor Wave Light', isDark: false, bg: '#fdf2f8', card: '#ffffff', accent: '#db2777' },

  // Legacy mappings for backwards-compatibility with previous saved user preferences
  { name: 'Dark Slate', isDark: true, bg: '#0c131a', card: '#131e29', accent: '#38bdf8' },
  { name: 'Midnight Purple', isDark: true, bg: '#0d0b18', card: '#19152e', accent: '#ec4899' },
  { name: 'Emerald Forest', isDark: true, bg: '#07140e', card: '#0f241a', accent: '#10b981' },
  { name: 'Cyber Amber', isDark: true, bg: '#141008', card: '#211a0d', accent: '#f59e0b' },
  { name: 'Light Canvas', isDark: false, bg: '#f1f5f9', card: '#ffffff', accent: '#0284c7' },
];

export const THEME_MAP: Record<string, ThemeMeta> = Object.fromEntries(THEMES.map((t) => [t.name, t]));
