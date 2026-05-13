import { cn } from '../lib/utils';

interface CardProps {
  children: React.ReactNode;
  className?: string;
  title?: string;
  subtitle?: string;
}

export const Card = ({ children, className, title, subtitle }: CardProps) => (
  <div className={cn("bg-surface border border-line rounded-sm flex flex-col overflow-hidden", className)}>
    {(title || subtitle) && (
      <div className="bg-header px-3 py-2 border-b border-line flex justify-between items-center">
        <h3 className="text-[10px] font-bold text-ink-bright uppercase tracking-widest">{title}</h3>
        {subtitle && <span className="mono-label">{subtitle}</span>}
      </div>
    )}
    <div className="p-3 flex-1 flex flex-col gap-3">
      {children}
    </div>
  </div>
);
