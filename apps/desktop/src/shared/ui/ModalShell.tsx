import { useEffect } from "react";
import type { ReactNode } from "react";
import { X } from "lucide-react";

type ModalSize = "sm" | "md" | "lg" | "xl";

const SIZE_CLASSES: Record<ModalSize, string> = {
  sm: "w-[440px]",
  md: "w-[560px]",
  lg: "w-[920px]",
  xl: "w-[1160px] h-[86vh]",
};

interface ModalShellProps {
  title: string;
  subtitle?: string;
  size?: ModalSize;
  onClose?: () => void;
  footer?: ReactNode;
  headerExtra?: ReactNode;
  children: ReactNode;
  noPadding?: boolean;
  className?: string;
  backdropClassName?: string;
}

export default function ModalShell({
  title,
  subtitle,
  size = "md",
  onClose,
  footer,
  headerExtra,
  children,
  noPadding = false,
  className = "",
  backdropClassName = "",
}: ModalShellProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose?.();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={e => {
        if (e.target === e.currentTarget) onClose?.();
      }}
      className={`fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-5 ${backdropClassName}`}
    >
      <div
        className={`${className ? `${className} ${className.includes("max-w-") ? "" : "max-w-[96vw]"} ${className.includes("max-h-") ? "" : "max-h-[92vh]"}` : `${SIZE_CLASSES[size]} max-w-[96vw] max-h-[92vh]`} bg-card border border-hairline rounded-sm flex flex-col overflow-hidden transition-all duration-200`}
      >
        <div className="px-4 py-2.5 bg-sidebar border-b border-subtle flex items-center justify-between gap-3 shrink-0">
          <div className="min-w-0 flex-1">
            <h2 className="text-sm font-semibold text-primary truncate">{title}</h2>
            {subtitle && <p className="text-xs text-secondary truncate mt-0.5">{subtitle}</p>}
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            {headerExtra}
            <button
              type="button"
              aria-label="Close modal"
              title="Close (Esc)"
              onClick={onClose}
              className="w-7 h-7 flex items-center justify-center rounded-xs text-secondary hover:text-primary hover:bg-elevated transition-colors"
            >
              <X className="w-4 h-4" strokeWidth={1.6} />
            </button>
          </div>
        </div>

        <div
          className={`flex-1 min-h-0 overflow-auto ${noPadding ? "flex flex-col" : "p-4 flex flex-col gap-3"}`}
        >
          {children}
        </div>

        {footer && (
          <div className="px-4 py-2.5 bg-sidebar border-t border-subtle flex items-center justify-end gap-2 shrink-0">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
