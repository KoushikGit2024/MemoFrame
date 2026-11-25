import { AlertCircle, CheckCircle2, Info } from 'lucide-react';
import { useApp } from '../context/AppContext';

export default function ToastContainer() {
  const { toasts } = useApp();
  if (!toasts.length) return null;

  return (
    <div className="fixed right-4 bottom-12 z-[60] flex flex-col gap-1.5 pointer-events-none">
      {toasts.map((t) => {
        const Icon = t.kind === 'success' ? CheckCircle2 : t.kind === 'error' ? AlertCircle : Info;
        const borderClass =
          t.kind === 'success'
            ? 'border-l-success'
            : t.kind === 'error'
            ? 'border-l-danger'
            : 'border-l-accent-secondary';
        const iconClass =
          t.kind === 'success'
            ? 'text-success'
            : t.kind === 'error'
            ? 'text-danger'
            : 'text-accent-secondary';

        return (
          <div
            key={t.id}
            className={`pointer-events-auto flex items-center gap-2 px-3 py-2 bg-elevated border border-hairline border-l-[3px] ${borderClass} rounded-xs text-xs text-primary max-w-[360px]`}
          >
            <Icon className={`w-3.5 h-3.5 shrink-0 ${iconClass}`} strokeWidth={1.7} />
            <span>{t.message}</span>
          </div>
        );
      })}
    </div>
  );
}
