import type { Config } from 'tailwindcss';

const withOpacity = (cssVar: string) => `rgb(var(${cssVar}) / <alpha-value>)`;

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        app: withOpacity('--bg-app-rgb'),
        sidebar: withOpacity('--bg-sidebar-rgb'),
        card: withOpacity('--bg-card-rgb'),
        elevated: withOpacity('--bg-elevated-rgb'),
        input: withOpacity('--bg-input-rgb'),
        hairline: withOpacity('--border-rgb'),
        subtle: withOpacity('--border-subtle-rgb'),
        primary: withOpacity('--text-primary-rgb'),
        secondary: withOpacity('--text-secondary-rgb'),
        accent: withOpacity('--accent-rgb'),
        'accent-hover': 'var(--accent-hover)',
        'accent-light': 'var(--accent-light)',
        'accent-text': 'var(--accent-text)',
        'accent-secondary': withOpacity('--accent-secondary-rgb'),
        'accent-secondary-hover': 'var(--accent-secondary-hover)',
        'accent-secondary-light': 'var(--accent-secondary-light)',
        'accent-secondary-text': 'var(--accent-secondary-text)',
        violet: withOpacity('--color-violet-rgb'),
        'violet-hover': 'var(--color-violet-hover)',
        'violet-bg': 'var(--color-violet-bg)',
        'violet-text': 'var(--color-violet-text)',
        amber: withOpacity('--color-amber-rgb'),
        'amber-hover': 'var(--color-amber-hover)',
        'amber-bg': 'var(--color-amber-bg)',
        'amber-text': 'var(--color-amber-text)',
        danger: withOpacity('--danger-rgb'),
        'danger-hover': 'var(--danger-hover)',
        'danger-bg': 'var(--danger-bg)',
        'danger-text': 'var(--danger-text)',
        success: withOpacity('--success-rgb'),
        'success-hover': 'var(--success-hover)',
        'success-bg': 'var(--success-bg)',
        'success-text': 'var(--success-text)',
        badge: withOpacity('--badge-bg-rgb'),
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
