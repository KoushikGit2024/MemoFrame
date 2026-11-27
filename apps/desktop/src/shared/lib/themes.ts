import type { ThemeMeta } from "../types/memoframe";

export interface ThemeFamily {
  id: string;
  label: string;
  tagline: string;
  darkTheme: string;
  lightTheme: string;
  previewAccent: string;
  previewSecondary: string;
  previewTertiary: string;
  previewQuaternary: string;
}

export const THEME_FAMILIES: ReadonlyArray<ThemeFamily> = [
  {
    id: "studio-graphite",
    label: "Studio Graphite",
    tagline: "Terracotta · Teal · Cobalt",
    darkTheme: "Studio Graphite Dark",
    lightTheme: "Studio Graphite Light",
    previewAccent: "#e85d3f",
    previewSecondary: "#14b8a6",
    previewTertiary: "#6366f1",
    previewQuaternary: "#eab308",
  },
  {
    id: "kyoto-ink",
    label: "Kyoto Ink",
    tagline: "Crimson · Jade · Persimmon",
    darkTheme: "Kyoto Ink Dark",
    lightTheme: "Kyoto Ink Light",
    previewAccent: "#e11d48",
    previewSecondary: "#0d9488",
    previewTertiary: "#d97706",
    previewQuaternary: "#9333ea",
  },
  {
    id: "bauhaus-signal",
    label: "Bauhaus Signal",
    tagline: "Cobalt · Vermilion · Ochre",
    darkTheme: "Bauhaus Signal Dark",
    lightTheme: "Bauhaus Signal Light",
    previewAccent: "#2563eb",
    previewSecondary: "#ea580c",
    previewTertiary: "#ca8a04",
    previewQuaternary: "#10b981",
  },
  {
    id: "botanical-copper",
    label: "Botanical Copper",
    tagline: "Copper · Pine Teal · Berry",
    darkTheme: "Botanical Copper Dark",
    lightTheme: "Botanical Copper Light",
    previewAccent: "#d97706",
    previewSecondary: "#0f766e",
    previewTertiary: "#db2777",
    previewQuaternary: "#22c55e",
  },
  {
    id: "desert-ochre",
    label: "Desert Ochre",
    tagline: "Sienna · Cerulean · Olive",
    darkTheme: "Desert Ochre Dark",
    lightTheme: "Desert Ochre Light",
    previewAccent: "#ea580c",
    previewSecondary: "#0284c7",
    previewTertiary: "#65a30d",
    previewQuaternary: "#fbbf24",
  },
  {
    id: "nordic-fjord",
    label: "Nordic Fjord",
    tagline: "Glacier · Coral · Honey",
    darkTheme: "Nordic Fjord Dark",
    lightTheme: "Nordic Fjord Light",
    previewAccent: "#0284c7",
    previewSecondary: "#f43f5e",
    previewTertiary: "#eab308",
    previewQuaternary: "#34d399",
  },
];

export const THEMES: ReadonlyArray<ThemeMeta> = [
  { name: "Studio Graphite Dark", isDark: true, bg: "#0d1014", card: "#151a21", accent: "#e85d3f" },
  { name: "Studio Graphite Light", isDark: false, bg: "#f4f5f7", card: "#ffffff", accent: "#d9482a" },
  { name: "Kyoto Ink Dark", isDark: true, bg: "#121010", card: "#1b1817", accent: "#f43f5e" },
  { name: "Kyoto Ink Light", isDark: false, bg: "#faf7f4", card: "#ffffff", accent: "#be123c" },
  { name: "Bauhaus Signal Dark", isDark: true, bg: "#0f1115", card: "#171b22", accent: "#3b82f6" },
  { name: "Bauhaus Signal Light", isDark: false, bg: "#f6f7f9", card: "#ffffff", accent: "#1d4ed8" },
  { name: "Botanical Copper Dark", isDark: true, bg: "#0c1210", card: "#131d19", accent: "#f59e0b" },
  { name: "Botanical Copper Light", isDark: false, bg: "#f3f7f4", card: "#ffffff", accent: "#b45309" },
  { name: "Desert Ochre Dark", isDark: true, bg: "#14110e", card: "#1e1915", accent: "#f97316" },
  { name: "Desert Ochre Light", isDark: false, bg: "#fbf8f3", card: "#ffffff", accent: "#c2410c" },
  { name: "Nordic Fjord Dark", isDark: true, bg: "#0b1218", card: "#131e28", accent: "#38bdf8" },
  { name: "Nordic Fjord Light", isDark: false, bg: "#f3f6fa", card: "#ffffff", accent: "#0369a1" },
];

export const THEME_MAP: Record<string, ThemeMeta> = Object.fromEntries([
  ...THEMES.map(t => [t.name, t]),
  // Legacy theme name aliases so existing user preferences migrate seamlessly
  ["Dark Slate", THEMES[0]],
  ["Nordic Slate Dark", THEMES[0]],
  ["Light Canvas", THEMES[1]],
  ["Nordic Slate Light", THEMES[1]],
  ["Obsidian Rose Dark", THEMES[2]],
  ["Obsidian Rose Light", THEMES[3]],
  ["Neon Cyberpunk Dark", THEMES[4]],
  ["Neon Cyberpunk Light", THEMES[5]],
  ["Emerald Forest", THEMES[6]],
  ["Alpine Emerald Dark", THEMES[6]],
  ["Alpine Emerald Light", THEMES[7]],
  ["Cyber Amber", THEMES[8]],
  ["Solar Flare Dark", THEMES[8]],
  ["Solar Flare Light", THEMES[9]],
  ["Midnight Purple", THEMES[10]],
  ["Vapor Wave Dark", THEMES[10]],
  ["Vapor Wave Light", THEMES[11]],
]);
