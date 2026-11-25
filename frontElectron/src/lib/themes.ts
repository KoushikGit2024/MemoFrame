import type { ThemeMeta } from '../types/memoframe';

export const THEMES: ThemeMeta[] = [
  { name: 'Dark Slate', isDark: true, bg: '#0f1216', card: '#161b22', accent: '#2f81f7' },
  { name: 'Midnight Purple', isDark: true, bg: '#0e0d16', card: '#171525', accent: '#8b5cf6' },
  { name: 'Emerald Forest', isDark: true, bg: '#0b130f', card: '#121e18', accent: '#10b981' },
  { name: 'Cyber Amber', isDark: true, bg: '#121212', card: '#1b1b1b', accent: '#f59e0b' },
  { name: 'Light Canvas', isDark: false, bg: '#f4f6f9', card: '#ffffff', accent: '#0969da' },
];

export const THEME_MAP: Record<string, ThemeMeta> = Object.fromEntries(THEMES.map((t) => [t.name, t]));
