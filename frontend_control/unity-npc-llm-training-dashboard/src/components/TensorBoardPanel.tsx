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

interface TensorBoardPanelProps {
  analyticsData: Array<{ step: number; loss: number; acc: number; lr: number }>;
  onRefresh: () => void;
}

export const TensorBoardPanel = ({ analyticsData, onRefresh }: TensorBoardPanelProps) => (
  <motion.div
    key="analytics"
    initial={{ opacity: 0, scale: 0.98 }}
    animate={{ opacity: 1, scale: 1 }}
    exit={{ opacity: 0, scale: 0.98 }}
    className="flex-1 overflow-hidden p-4 flex flex-col gap-4"
  >
    <div className="flex justify-between items-end">
      <h3 className="text-xs font-bold text-ink-bright uppercase tracking-widest">LoRA SCALARS: TRAINING_ACCURACY & LOSS</h3>
      <div className="flex gap-4 text-[10px] items-center">
        <div className="flex items-center gap-1.5"><div className="w-2 h-2 bg-accent rounded-sm" /> <span>Current Run</span></div>
        <div className="flex items-center gap-1.5"><div className="w-2 h-2 bg-line rounded-sm" /> <span>Baseline</span></div>
        <button onClick={onRefresh} className="text-accent underline font-mono">Refresh API</button>
      </div>
    </div>

    <div className="grid grid-cols-2 gap-4 flex-1 overflow-auto custom-scrollbar">
      <Card title="Model Loss (Smooth: 0.6)" subtitle="TAG: TRAIN/LOSS">
        <div className="h-64 mt-4">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={analyticsData}>
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
      </Card>

      <Card title="Validation Accuracy" subtitle="TAG: EVAL/ACC">
        <div className="h-64 mt-4">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={analyticsData}>
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
      </Card>

      <Card title="Learning Rate Scheduler" subtitle="TAG: OPTIM/LR" className="col-span-2">
        <div className="h-48 mt-4">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={analyticsData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" opacity={0.3} />
              <XAxis dataKey="step" stroke="var(--ink)" fontSize={9} opacity={0.5} />
              <YAxis stroke="var(--ink)" fontSize={9} opacity={0.5} />
              <Line type="stepAfter" dataKey="lr" stroke="var(--warning)" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </div>
  </motion.div>
);
