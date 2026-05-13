import { cn } from '../lib/utils';

interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'success' | 'warning' | 'danger';
  className?: string;
}

export const Badge = ({ children, variant = 'default', className }: BadgeProps) => {
  const styles = {
    default: "bg-line text-ink/60 border-line/50",
    success: "bg-success/10 text-success border-success/30 shadow-[0_0_8px_rgba(16,185,129,0.1)]",
    warning: "bg-warning/10 text-warning border-warning/30 shadow-[0_0_8px_rgba(245,158,11,0.1)]",
    danger: "bg-danger/10 text-danger border-danger/30 shadow-[0_0_8px_rgba(239,68,68,0.1)]",
  };
  return (
    <span className={cn("px-1.5 py-0.5 rounded-sm text-[9px] font-bold border uppercase tracking-tight transition-all duration-300", styles[variant], className)}>
      {children}
    </span>
  );
};
