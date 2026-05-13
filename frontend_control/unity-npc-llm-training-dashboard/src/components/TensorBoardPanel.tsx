import { motion } from 'motion/react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
} from 'recharts';
import { Card } from './Card';
import { cn } from '../lib/utils';

interface TensorBoardPanelProps {
  data: Array<{ step: number; loss: number; acc: number; lr: number }>;
  onRefresh: () => void;
  isLive?: boolean;
  isFallback?: boolean;
}

const EmptyChart = ({ message }: { message: string }) => (
  <div className="h-64 mt-4 flex items-center justify-center text-ink/40 text-[11px] font-mono">
    {message}
  </div>
);

export const TensorBoardPanel = ({ data, onRefresh, isLive, isFallback }: TensorBoardPanelProps) => (
  <motion.div
    key="analytics"
    initial={{ opacity: 0, scale: 0.98 }}
    animate={{ opacity: 1, scale: 1 }}
    exit={{ opacity: 0, scale: 0.98 }}
    className="flex-1 overflow-hidden p-4 flex flex-col gap-4"
  >
    <div className="flex justify-between items-end">
      <div className="flex items-center gap-3">
        <h3 className="text-xs font-bold text-ink-bright uppercase tracking-widest">LoRA SCALARS: TRAINING_ACCURACY & LOSS</h3>
        {isFallback && (
          <span className="text-[9px] bg-warning/20 text-warning border border-warning/40 px-2 py-0.5 rounded-sm font-mono font-bold uppercase tracking-wider">
            Using estimated data — TB files not found
          </span>
        )}
      </div>
      <div className="flex gap-4 text-[10px] items-center">
        <div className="flex items-center gap-1.5"><div className="w-2 h-2 bg-accent rounded-sm" /> <span>Current Run</span></div>
        <div className="flex items-center gap-1.5"><div className="w-2 h-2 bg-line rounded-sm" /> <span>Baseline</span></div>
        <div className="flex items-center gap-2">
          {isLive && (
            <span className="flex items-center gap-1 text-success font-bold font-mono">
              <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse shadow-[0_0_6px_var(--success)]" />
              LIVE
            </span>
          )}
          <button onClick={onRefresh} className="text-accent underline font-mono">Refresh API</button>
        </div>
      </div>
    </div>

    <div className="grid grid-cols-2 gap-4 flex-1 overflow-auto custom-scrollbar">
      <Card title="Model Loss (Smooth: 0.6)" subtitle="TAG: TRAIN/LOSS">
        {data.length === 0 ? (
          <EmptyChart message="No training data available" />
        ) : (
          <div className="h-64 mt-4">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" opacity={0.3} />
                <XAxis dataKey="step" stroke="var(--ink)" fontSize={9} opacity={0.5} />
                <YAxis stroke="var(--ink)" fontSize={9} opacity={0.5} />
                <Tooltip
                  contentStyle={{ background: 'var(--header)', border: '1px solid var(--line)', borderRadius: '4px', fontSize: '10px' }}
                />
                <Line type="monotone" dataKey="loss" stroke="var(--accent)" strokeWidth={2} dot={{ r: 2 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>

      <Card title="Validation Accuracy" subtitle="TAG: EVAL/ACC">
        {data.length === 0 ? (
          <EmptyChart message="No training data available" />
        ) : (
          <div className="h-64 mt-4">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data}>
                <defs>
                  <linearGradient id="colorAcc" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--success)" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="var(--success)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" opacity={0.3} />
                <XAxis dataKey="step" stroke="var(--ink)" fontSize={9} opacity={0.5} />
                <YAxis stroke="var(--ink)" fontSize={9} opacity={0.5} />
                <Tooltip
                  contentStyle={{ background: 'var(--header)', border: '1px solid var(--line)', borderRadius: '4px', fontSize: '10px' }}
                />
                <Area type="monotone" dataKey="acc" stroke="var(--success)" fillOpacity={1} fill="url(#colorAcc)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>

      <Card title="Learning Rate Scheduler" subtitle="TAG: OPTIM/LR" className="col-span-2">
        {data.length === 0 ? (
          <EmptyChart message="No training data available" />
        ) : (
          <div className="h-48 mt-4">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" opacity={0.3} />
                <XAxis dataKey="step" stroke="var(--ink)" fontSize={9} opacity={0.5} />
                <YAxis stroke="var(--ink)" fontSize={9} opacity={0.5} />
                <Line type="stepAfter" dataKey="lr" stroke="var(--warning)" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>
    </div>
  </motion.div>
);
