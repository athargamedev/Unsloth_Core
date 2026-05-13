import { useState, useEffect } from 'react';
import { fetchJson } from '../api';
import { Card } from './Card';
import { Badge } from './Badge';
import { Wifi, WifiOff, Settings } from 'lucide-react';

interface RemoteConfig {
  configured: boolean;
  remoteUrl: string;
  hasKey: boolean;
  mode: 'local' | 'remote';
}

export function RemoteConfigPanel() {
  const [config, setConfig] = useState<RemoteConfig | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchConfig = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchJson<RemoteConfig>('/api/remote-config');
      setConfig(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => { fetchConfig(); }, []);

  return (
    <Card title="Remote Execution" subtitle="Configure remote runner">
      <div className="space-y-3">
        {/* Status */}
        <div className="flex items-center gap-2">
          {config?.configured ? (
            <span className="flex items-center gap-1 text-[10px] text-success font-mono">
              <Wifi className="w-3 h-3" /> Remote configured
            </span>
          ) : (
            <span className="flex items-center gap-1 text-[10px] text-warning font-mono">
              <WifiOff className="w-3 h-3" /> Not configured
            </span>
          )}
          <Badge variant={config?.mode === 'local' ? 'default' : 'warning'}>
            {config?.mode?.toUpperCase() || 'LOCAL'}
          </Badge>
        </div>

        {/* Instructions */}
        <div className="p-2 bg-panel border border-line rounded text-[10px] text-ink/60 space-y-1">
          <p className="font-bold text-ink/80">To enable remote mode:</p>
          <p>1. Set environment variables:</p>
          <code className="block bg-black/20 px-2 py-1 rounded font-mono text-[9px] mt-1">
            REMOTE_API_URL=https://your-server.com<br />
            REMOTE_API_KEY=your-api-key
          </code>
          <p className="mt-2">2. Restart the server</p>
          <p className="mt-2">3. Toggle to Remote mode in the System Hub</p>
        </div>

        {/* Current settings */}
        {config && (
          <div className="space-y-1 text-[10px] font-mono">
            <div className="flex justify-between">
              <span className="text-ink/40">Remote URL:</span>
              <span className="text-ink/60">{config.remoteUrl || '(not set)'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-ink/40">API Key:</span>
              <span className="text-ink/60">{config.hasKey ? '••••••••' : '(not set)'}</span>
            </div>
          </div>
        )}

        {isLoading && <div className="text-[10px] text-ink/40">Loading...</div>}
        {error && <div className="text-[10px] text-danger">Error: {error}</div>}
      </div>
    </Card>
  );
}
