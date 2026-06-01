import { cn } from '../lib/utils';

interface CardProps {
  children: React.ReactNode;
  className?: string;
  title?: string;
  subtitle?: string;
}

export const Card = ({ children, className, title, subtitle }: CardProps) => (
  <div className={cn("glass-panel w-full min-w-0 min-h-0 rounded flex flex-col overflow-hidden transition-all duration-500 hover:shadow-accent/5", className)}>
    {(title || subtitle) && (
      <div className="bg-header/50 px-3 py-2.5 border-b border-line flex flex-wrap gap-2 justify-between items-center backdrop-blur-md min-w-0">
        <h3 className="text-[10px] font-bold text-ink-bright/90 uppercase tracking-widest min-w-0">{title}</h3>
        {subtitle && <span className="mono-label text-accent/80 max-w-full truncate">{subtitle}</span>}
      </div>
    )}
    <div className="p-4 flex-1 flex flex-col gap-4 min-w-0 min-h-0">
      {children}
    </div>
  </div>
);
