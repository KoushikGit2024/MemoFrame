import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        app: 'var(--bg-app)',
        sidebar: 'var(--bg-sidebar)',
        card: 'var(--bg-card)',
        elevated: 'var(--bg-elevated)',
        input: 'var(--bg-input)',
        hairline: 'var(--border)',
        subtle: 'var(--border-subtle)',
        primary: 'var(--text-primary)',
        secondary: 'var(--text-secondary)',
        accent: 'var(--accent)',
        'accent-hover': 'var(--accent-hover)',
        'accent-light': 'var(--accent-light)',
        'accent-text': 'var(--accent-text)',
        danger: 'var(--danger)',
        'danger-bg': 'var(--danger-bg)',
        success: 'var(--success)',
        'success-bg': 'var(--success-bg)',
        badge: 'var(--badge-bg)',
      },
      borderRadius: {
        xs: '2px',
        sm: '3px',
        md: '4px',
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Inter', 'Roboto', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', '"Cascadia Mono"', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
};

export default config;
