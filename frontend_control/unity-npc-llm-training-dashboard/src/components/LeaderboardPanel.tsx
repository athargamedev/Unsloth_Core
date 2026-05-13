import { useState, useEffect } from 'react';
import { fetchJson } from '../api';
import type { SupabaseLeaderboardEntry, SupabaseStatus } from '../api';
import { Card } from './Card';
import { Trophy, RefreshCw, Wifi, WifiOff, AlertCircle } from 'lucide-react';

export function LeaderboardPanel() {
  const [entries, setEntries] = useState<SupabaseLeaderboardEntry[]>([]);
  const [status, setStatus] = useState<SupabaseStatus>({ connected: false, url: '', error: 'Loading...' });
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchLeaderboard = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchJson<{ entries: SupabaseLeaderboardEntry[]; status: SupabaseStatus }>('/api/supabase/leaderboard');
      setEntries(data.entries || []);
      setStatus(data.status);
    } catch (err: any) {
      setError(err.message);
      setStatus({ connected: false, url: '', error: err.message });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => { fetchLeaderboard(); }, []);

  return (
    <Card title="Supabase Leaderboard" subtitle="Top model evaluations">
      <div className="space-y-3">
        {/* Status bar */}
        <div className="flex items-center justify-between text-[10px] font-mono">
          <div className="flex items-center gap-2">
            {status.connected ? (
              <span className="flex items-center gap-1 text-success">
                <Wifi className="w-3 h-3" /> Connected
              </span>
            ) : (
              <span className="flex items-center gap-1 text-danger">
                <WifiOff className="w-3 h-3" /> Disconnected
              </span>
            )}
            {status.error && status.error !== 'Loading...' && (
              <span className="text-warning flex items-center gap-1">
                <AlertCircle className="w-3 h-3" /> {status.error}
              </span>
            )}
          </div>
          <button onClick={fetchLeaderboard} disabled={isLoading} className="text-ink/40 hover:text-ink/80 transition-colors disabled:opacity-40">
            <RefreshCw className={`w-3 h-3 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {/* Entries */}
        {isLoading ? (
          <div className="text-[10px] text-ink/40 text-center py-8">Loading leaderboard...</div>
        ) : entries.length === 0 ? (
          <div className="text-[10px] text-ink/40 text-center py-8">
            {status.connected ? 'No test results found. Run an evaluation first.' : 'Supabase not connected. Configure SUPABASE_URL and SUPABASE_KEY.'}
          </div>
        ) : (
          <div className="space-y-1">
            {entries.map((entry) => (
              <div key={`${entry.npc_id}-${entry.test_name}`} className="flex items-center justify-between p-2 bg-panel border border-line rounded hover:border-accent/30 transition-colors">
                <div className="flex items-center gap-3">
                  {/* Rank medal */}
                  <div className="w-5 h-5 flex items-center justify-center">
                    {entry.rank === 1 ? (
                      <Trophy className="w-4 h-4 text-yellow-400" />
                    ) : entry.rank === 2 ? (
                      <Trophy className="w-4 h-4 text-gray-300" />
                    ) : entry.rank === 3 ? (
                      <Trophy className="w-4 h-4 text-amber-600" />
                    ) : (
                      <span className="text-[10px] font-mono text-ink/40">{entry.rank}</span>
                    )}
                  </div>
                  <div>
                    <div className="text-[10px] font-bold text-ink-bright">{entry.npc_name}</div>
                    <div className="text-[8px] font-mono text-ink/40">{entry.test_name} · {entry.npc_id}</div>
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-[12px] font-bold font-mono">{(entry.score * 100).toFixed(0)}%</div>
                  <div className="text-[8px] text-ink/40">Score</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Card>
  );
}
