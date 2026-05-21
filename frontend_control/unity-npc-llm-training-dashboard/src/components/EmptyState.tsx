import type { ReactNode } from 'react';
import { cn } from '../lib/utils';

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cn('flex flex-col items-center justify-center py-12 px-4', className)}>
      {icon && <div className="text-ink/20 mb-4">{icon}</div>}
      <h3 className="text-sm font-semibold text-ink/60 mb-1 text-center">{title}</h3>
      {description && (
        <p className="text-[12px] text-ink/40 text-center max-w-md leading-relaxed">
          {description}
        </p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
