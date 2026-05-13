import { useState, useEffect } from 'react';
import { fetchJson } from '../api';
import { Card } from './Card';
import { Badge } from './Badge';
import { Upload, FileText, FolderOpen, ExternalLink, RefreshCw, Box } from 'lucide-react';

interface UnityStatus {
  exported: Array<{
    npcKey: string;
    ggufFiles: Array<{ name: string; sizeMB: number; quant: string }>;
    manifest: Record<string, unknown>;
  }>;
  unityProject: string | null;
  deployedFiles: string[];
  deployScript: boolean;
}

export function UnityDeployPanel() {
  const [status, setStatus] = useState<UnityStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deployOutput, setDeployOutput] = useState<string | null>(null);
  const [isDeploying, setIsDeploying] = useState(false);

  const fetchStatus = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchJson<UnityStatus>('/api/unity/status');
      setStatus(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => { fetchStatus(); }, []);

  const handleDeploy = async (dryRun: boolean) => {
    setIsDeploying(true);
    setDeployOutput(null);
    try {
      const resp = await fetch('/api/unity/deploy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dryRun }),
      });
      const data = await resp.json();
      setDeployOutput(data.output || (data.success ? 'Deploy succeeded' : 'Deploy failed'));
    } catch (err: any) {
      setDeployOutput(`Error: ${err.message}`);
    } finally {
      setIsDeploying(false);
    }
  };

  const totalGgufs = status?.exported.reduce((acc, n) => acc + n.ggufFiles.length, 0) || 0;

  return (
    <Card title="Unity Deployment" subtitle="Export & deploy status">
      <div className="space-y-3">
        {/* Summary */}
        <div className="flex gap-2 text-[10px] font-mono">
          <div className="flex-1 p-2 bg-panel border border-line rounded">
            <div className="text-ink/40 text-[8px] uppercase tracking-wider">Exported NPCs</div>
            <div className="text-ink-bright font-bold">{status?.exported.length || 0}</div>
          </div>
          <div className="flex-1 p-2 bg-panel border border-line rounded">
            <div className="text-ink/40 text-[8px] uppercase tracking-wider">GGUF Files</div>
            <div className="text-ink-bright font-bold">{totalGgufs}</div>
          </div>
          <div className="flex-1 p-2 bg-panel border border-line rounded">
            <div className="text-ink/40 text-[8px] uppercase tracking-wider">Deployed</div>
            <div className="text-ink-bright font-bold">{status?.deployedFiles.length || 0}</div>
          </div>
        </div>

        {/* Unity Project */}
        <div className="p-2 bg-panel border border-line rounded flex items-center gap-2">
          <FolderOpen className="w-3 h-3 text-ink/40" />
          <span className="text-[10px] font-mono text-ink/60 flex-1 truncate">
            {status?.unityProject ? status.unityProject : 'No Unity project detected'}
          </span>
          {status?.unityProject && <span className="text-success"><Badge variant="success">Detected</Badge></span>}
        </div>

        {/* NPC Export List */}
        {status && status.exported.length > 0 && (
          <div className="space-y-1 max-h-[200px] overflow-auto">
            {status.exported.map((npc) => (
              <details key={npc.npcKey} className="text-[10px]">
                <summary className="cursor-pointer text-ink-bright font-bold hover:text-accent">
                  {npc.npcKey} ({npc.ggufFiles.length} files)
                </summary>
                <div className="ml-3 mt-1 space-y-1">
                  {npc.ggufFiles.map((f) => (
                    <div key={f.name} className="flex justify-between items-center p-1 bg-bg/50 rounded">
                      <span className="font-mono text-ink/60 truncate">{f.name}</span>
                      <span className="text-ink/40">{f.sizeMB}MB · {f.quant}</span>
                    </div>
                  ))}
                  {npc.manifest && Object.keys(npc.manifest).length > 0 && (
                    <div className="text-ink/40 italic">Has manifest ✓</div>
                  )}
                </div>
              </details>
            ))}
          </div>
        )}

        {/* Deployed Files */}
        {status && status.deployedFiles.length > 0 && (
          <div>
            <div className="text-[9px] font-bold text-ink/40 uppercase tracking-wider mb-1">Deployed to Unity</div>
            <div className="space-y-1">
              {status.deployedFiles.map((file, i) => (
                <div key={i} className="flex items-center gap-2 text-[10px] font-mono text-ink/60">
                  <FileText className="w-3 h-3 text-success" />
                  {file}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Deploy Actions */}
        <div className="flex gap-2">
          <button
            onClick={() => handleDeploy(true)}
            disabled={isDeploying}
            className="flex items-center gap-1 px-3 py-1.5 text-[10px] font-bold bg-panel border border-line rounded hover:border-accent transition-colors disabled:opacity-40"
          >
            <RefreshCw className={`w-3 h-3 ${isDeploying ? 'animate-spin' : ''}`} />
            Dry Run
          </button>
          <button
            onClick={() => handleDeploy(false)}
            disabled={isDeploying || !status?.deployScript}
            className="flex items-center gap-1 px-3 py-1.5 text-[10px] font-bold bg-accent text-bg rounded hover:bg-accent/80 transition-colors disabled:opacity-40"
          >
            <Upload className="w-3 h-3" />
            Deploy All
          </button>
          <button onClick={fetchStatus} className="px-2 py-1.5 text-[10px] text-ink/40 hover:text-ink/80" title="Refresh">
            <RefreshCw className="w-3 h-3" />
          </button>
        </div>

        {/* Deploy Output */}
        {deployOutput && (
          <div className="p-2 bg-black/40 border border-line rounded text-[9px] font-mono text-ink/60 max-h-[150px] overflow-auto">
            <div className="text-[8px] font-bold text-ink/40 uppercase mb-1">Output</div>
            <pre className="whitespace-pre-wrap">{deployOutput}</pre>
          </div>
        )}

        {error && <div className="text-[10px] text-danger">Error: {error}</div>}
      </div>
    </Card>
  );
}
