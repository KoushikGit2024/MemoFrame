import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: ReactNode;
}

export default function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center py-12 px-5 text-secondary gap-2">
      {Icon && <Icon className="w-8 h-8 opacity-50" strokeWidth={1.4} />}
      <h3 className="text-sm font-semibold text-primary mt-1">{title}</h3>
      {description && <p className="text-xs text-secondary max-w-sm">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
