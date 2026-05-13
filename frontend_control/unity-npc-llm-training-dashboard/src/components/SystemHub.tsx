import { motion } from 'motion/react';
import { Zap, ExternalLink, Layers, XCircle, Database, Shield } from 'lucide-react';
import { cn } from '../lib/utils';
import { Card } from './Card';
import type { AvailableCommand } from '../api';

interface SystemHubProps {
  availableCommands: AvailableCommand[];
  onTriggerCommand: (cmd: AvailableCommand) => Promise<void>;
}

export const SystemHub = ({ availableCommands, onTriggerCommand }: SystemHubProps) => (
  <motion.div
    key="commands"
    initial={{ opacity: 0, y: 10 }}
    animate={{ opacity: 1, y: 0 }}
    exit={{ opacity: 0, y: -10 }}
    className="flex-1 overflow-hidden p-4 flex flex-col gap-6"
  >
    <div className="flex justify-between items-end">
      <h3 className="text-xs font-bold text-ink-bright uppercase tracking-widest">Global System Command Hub</h3>
      <p className="text-[10px] text-ink/40 font-mono italic">Direct Access to Core PIDs and Asset Handlers</p>
    </div>

    <div className="grid grid-cols-3 gap-4">
      {availableCommands.map((cmd) => (
        <button
          key={cmd.id}
          onClick={() => onTriggerCommand(cmd)}
          className={cn(
            "p-4 border border-line rounded flex flex-col items-center gap-3 transition-all hover:scale-[1.02] active:scale-95 group",
            cmd.color === 'accent' ? "hover:border-accent bg-accent/5" :
            cmd.color === 'success' ? "hover:border-success bg-success/5" :
            cmd.color === 'warning' ? "hover:border-warning bg-warning/5" :
            cmd.color === 'danger' ? "hover:border-danger bg-danger/5" : "hover:border-ink bg-panel",
          )}
        >
          <div className={cn(
            "p-2 rounded-sm border border-line transition-colors",
            cmd.color === 'accent' ? "text-accent border-accent/20" :
            cmd.color === 'success' ? "text-success border-success/20" :
            cmd.color === 'warning' ? "text-warning border-warning/20" :
            cmd.color === 'danger' ? "text-danger border-danger/20" : "text-ink/40",
          )}>
            {cmd.icon === 'zap' && <Zap className="w-5 h-5" />}
            {cmd.icon === 'external-link' && <ExternalLink className="w-5 h-5" />}
            {cmd.icon === 'layers' && <Layers className="w-5 h-5" />}
            {cmd.icon === 'x-circle' && <XCircle className="w-5 h-5" />}
            {cmd.icon === 'database' && <Database className="w-5 h-5" />}
            {cmd.icon === 'shield' && <Shield className="w-5 h-5" />}
          </div>
          <span className="text-[11px] font-bold uppercase tracking-tighter text-ink-bright text-center">{cmd.label}</span>
          <span className="text-[8px] opacity-30 font-mono">READY_EXEC</span>
        </button>
      ))}
    </div>

    <Card title="Quick Terminal Access" subtitle="SH_ROOT@NPC_CORE">
      <div className="bg-black/60 rounded p-4 font-mono text-[11px] text-accent/80 space-y-2 h-48 overflow-y-auto custom-scrollbar">
        <div className="flex gap-2">
          <span className="text-success">$</span>
          <span>ssh-agent auth --key=/mnt/vram/core_v4</span>
        </div>
        <div className="text-ink/40">[AUTH] RSA_TOKEN_VALIDATED (A100_NODE_X2)</div>
        <div className="flex gap-2">
          <span className="text-success">$</span>
          <span className="animate-pulse">_</span>
        </div>
      </div>
    </Card>
  </motion.div>
);
