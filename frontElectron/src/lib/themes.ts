import type { ThemeMeta } from "../types/memoframe";

export interface ThemeFamily {
  id: string;
  label: string;
  darkTheme: string;
  lightTheme: string;
  previewAccent: string;
  previewSecondary: string;
  previewTertiary: string;
  previewQuaternary: string;
  previewBgDark: string;
  previewBgLight: string;
}

export const THEME_FAMILIES: ThemeFamily[] = [
  {
    id: "nordic",
    label: "Nordic Slate",
    darkTheme: "Nordic Slate Dark",
    lightTheme: "Nordic Slate Light",
    previewAccent: "#5ca9f8",
    previewSecondary: "#38d9c0",
    previewTertiary: "#b598f7",
    previewQuaternary: "#e8a84a",
    previewBgDark: "#0a0e13",
    previewBgLight: "#f3f5f8",
  },
  {
    id: "obsidian",
    label: "Obsidian Rose",
    darkTheme: "Obsidian Rose Dark",
    lightTheme: "Obsidian Rose Light",
    previewAccent: "#f2467c",
    previewSecondary: "#28d5e8",
    previewTertiary: "#9d8cff",
    previewQuaternary: "#f0b132",
    previewBgDark: "#0c0d11",
    previewBgLight: "#f7f5f7",
  },
  {
    id: "cyberpunk",
    label: "Neon Cyberpunk",
    darkTheme: "Neon Cyberpunk Dark",
    lightTheme: "Neon Cyberpunk Light",
    previewAccent: "#f042a8",
    previewSecondary: "#19e0dc",
    previewTertiary: "#a875ff",
    previewQuaternary: "#e5cc29",
    previewBgDark: "#080911",
    previewBgLight: "#f2f4fa",
  },
  {
    id: "forest",
    label: "Alpine Emerald",
    darkTheme: "Alpine Emerald Dark",
    lightTheme: "Alpine Emerald Light",
    previewAccent: "#1cc48e",
    previewSecondary: "#5cc4f5",
    previewTertiary: "#c98bf5",
    previewQuaternary: "#e8a938",
    previewBgDark: "#090d0b",
    previewBgLight: "#f3f7f4",
  },
  {
    id: "solar",
    label: "Solar Flare",
    darkTheme: "Solar Flare Dark",
    lightTheme: "Solar Flare Light",
    previewAccent: "#f27435",
    previewSecondary: "#2ad1c9",
    previewTertiary: "#a488f5",
    previewQuaternary: "#ebc137",
    previewBgDark: "#0f0c0a",
    previewBgLight: "#f9f6f1",
  },
  {
    id: "vapor",
    label: "Vapor Wave",
    darkTheme: "Vapor Wave Dark",
    lightTheme: "Vapor Wave Light",
    previewAccent: "#ed4c98",
    previewSecondary: "#36d9c3",
    previewTertiary: "#ba85ff",
    previewQuaternary: "#f5ae42",
    previewBgDark: "#0c0a14",
    previewBgLight: "#f7f4fa",
  },
];

export const THEMES: ThemeMeta[] = [
  // 1. Nordic Slate
  { name: "Nordic Slate Dark", isDark: true, bg: "#0a0e13", card: "#111721", accent: "#5ca9f8" },
  { name: "Nordic Slate Light", isDark: false, bg: "#f3f5f8", card: "#ffffff", accent: "#1e56a8" },

  // 2. Obsidian Rose
  { name: "Obsidian Rose Dark", isDark: true, bg: "#0c0d11", card: "#13151b", accent: "#f2467c" },
  { name: "Obsidian Rose Light", isDark: false, bg: "#f7f5f7", card: "#ffffff", accent: "#c72263" },

  // 3. Neon Cyberpunk
  { name: "Neon Cyberpunk Dark", isDark: true, bg: "#080911", card: "#101221", accent: "#f042a8" },
  {
    name: "Neon Cyberpunk Light",
    isDark: false,
    bg: "#f2f4fa",
    card: "#ffffff",
    accent: "#b81d78",
  },

  // 4. Alpine Emerald
  { name: "Alpine Emerald Dark", isDark: true, bg: "#090d0b", card: "#111814", accent: "#1cc48e" },
  {
    name: "Alpine Emerald Light",
    isDark: false,
    bg: "#f3f7f4",
    card: "#ffffff",
    accent: "#0a7d5c",
  },

  // 5. Solar Flare
  { name: "Solar Flare Dark", isDark: true, bg: "#0f0c0a", card: "#181411", accent: "#f27435" },
  { name: "Solar Flare Light", isDark: false, bg: "#f9f6f1", card: "#ffffff", accent: "#b84514" },

  // 6. Vapor Wave
  { name: "Vapor Wave Dark", isDark: true, bg: "#0c0a14", card: "#151222", accent: "#ed4c98" },
  { name: "Vapor Wave Light", isDark: false, bg: "#f7f4fa", card: "#ffffff", accent: "#b81f6a" },

  // Legacy mappings for backwards-compatibility with previous saved user preferences
  { name: "Dark Slate", isDark: true, bg: "#0a0e13", card: "#111721", accent: "#5ca9f8" },
  { name: "Midnight Purple", isDark: true, bg: "#0c0a14", card: "#151222", accent: "#ed4c98" },
  { name: "Emerald Forest", isDark: true, bg: "#090d0b", card: "#111814", accent: "#1cc48e" },
  { name: "Cyber Amber", isDark: true, bg: "#0f0c0a", card: "#181411", accent: "#f27435" },
  { name: "Light Canvas", isDark: false, bg: "#f3f5f8", card: "#ffffff", accent: "#1e56a8" },
];

export const THEME_MAP: Record<string, ThemeMeta> = Object.fromEntries(
  THEMES.map(t => [t.name, t])
);
