import { motion } from 'motion/react';
import type { LucideIcon } from 'lucide-react';
import { cn } from '../lib/utils';

export interface TabChip {
  label: string;
  tone?: 'accent' | 'success' | 'warning' | 'danger' | 'muted';
}

interface TabChromeProps {
  icon: LucideIcon;
  title: string;
  description: string;
  tip: string;
  chips?: TabChip[];
  status?: string;
  className?: string;
}

const toneClasses: Record<NonNullable<TabChip['tone']>, string> = {
  accent: 'border-accent/30 text-accent bg-accent/10',
  success: 'border-success/30 text-success bg-success/10',
  warning: 'border-warning/30 text-warning bg-warning/10',
  danger: 'border-danger/30 text-danger bg-danger/10',
  muted: 'border-line text-ink/45 bg-panel/60',
};

export const TabChrome = ({ icon: Icon, title, description, tip, chips = [], status, className }: TabChromeProps) => (
  <motion.div
    initial={{ opacity: 0, y: -8 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.18 }}
    className={cn('mx-4 mt-4 w-auto min-w-0 rounded-xl border border-line/70 bg-surface/70 backdrop-blur-md overflow-hidden', className)}
  >
    <div className="flex flex-col gap-4 p-4 xl:flex-row xl:items-center xl:justify-between min-w-0">
      <div className="flex min-w-0 items-start gap-3">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-accent/30 bg-accent/10 shadow-[0_0_24px_rgba(96,165,250,0.14)]">
          <Icon className="h-5 w-5 text-accent animate-pulse" />
        </div>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-[12px] font-bold uppercase tracking-[0.18em] text-ink-bright">{title}</h2>
            {status && <span className="rounded-full border border-line bg-bg/70 px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest text-ink/55">{status}</span>}
          </div>
          <p className="mt-1 max-w-3xl text-[11px] leading-relaxed text-ink/55 break-words">{description}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {chips.map((chip) => (
              <span key={`${chip.label}-${chip.tone || 'muted'}`} className={cn('rounded-full border px-2.5 py-1 text-[9px] font-bold uppercase tracking-widest', toneClasses[chip.tone || 'muted'])}>
                {chip.label}
              </span>
            ))}
          </div>
        </div>
      </div>

      <div className="flex w-full max-w-xl items-start gap-2 rounded-lg border border-warning/20 bg-warning/5 px-3 py-2 text-[10px] text-warning/90 xl:items-center">
        <span className="font-bold uppercase tracking-widest">Tip</span>
        <span className="text-warning/75">{tip}</span>
      </div>
    </div>
  </motion.div>
);
