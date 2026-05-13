import { cn } from '../lib/utils';

interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'success' | 'warning' | 'danger';
}

export const Badge = ({ children, variant = 'default' }: BadgeProps) => {
  const styles = {
    default: "bg-line text-ink/60 border-line/50",
    success: "bg-success/10 text-success border-success/30",
    warning: "bg-warning/10 text-warning border-warning/30",
    danger: "bg-danger/10 text-danger border-danger/30",
  };
  return (
    <span className={cn("px-1 py-0.5 rounded-xs text-[9px] font-bold border uppercase tracking-tighter", styles[variant])}>
      {children}
    </span>
  );
};
