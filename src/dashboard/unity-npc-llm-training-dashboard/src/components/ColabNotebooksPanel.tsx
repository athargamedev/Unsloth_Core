import { useState, useEffect } from 'react';
import { Card } from './Card';
import { Badge } from './Badge';
import { 
  BookOpen, 
  Download, 
  RefreshCw, 
  ExternalLink,
  Cpu,
  Database,
  Sliders
} from 'lucide-react';
import { fetchJson, type Job } from '../api';

interface NotebookFile {
  name: string;
  path: string;
  npcKey: string;
  preset: string;
  size: string;
  lastModified: string;
}

interface ColabNotebooksPanelProps {
  onTriggerCommand: (payload: {
    commandId: string;
    type: string;
    options: Record<string, string>;
  }) => Promise<void>;
  jobs: Job[];
}

export function ColabNotebooksPanel({ onTriggerCommand, jobs }: ColabNotebooksPanelProps) {
  const [notebooks, setNotebooks] = useState<NotebookFile[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Form states for regenerating notebooks
  const [specGlob, setSpecGlob] = useState('subjects/NPC_specs/*.json');
  const [presets, setPresets] = useState('fast-3b,premium-3b,premium-8b,safe-any');
  const [localVram, setLocalVram] = useState('4.0');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const fetchNotebooks = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchJson<NotebookFile[]>('/api/colab/notebooks');
      setNotebooks(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchNotebooks();
  }, []);

  // Auto-refresh when any pipeline or plan-batch job finishes
  useEffect(() => {
    const activeJobs = jobs.filter(j => j.commandId === 'plan-batch' && j.status === 'running');
    if (activeJobs.length === 0 && !isLoading) {
      fetchNotebooks();
    }
  }, [jobs]);

  const handleRegenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await onTriggerCommand({
        commandId: 'plan-batch',
        type: 'Pipeline',
        options: {
          specGlob,
          presets,
          localVram,
        }
      });
    } catch (err: any) {
      setError(err.message || 'Failed to start notebook generation.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDownload = (pathStr: string, filename: string) => {
    const url = `/api/colab/download?path=${encodeURIComponent(pathStr)}`;
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const runningPlanJob = jobs.find(j => j.commandId === 'plan-batch' && j.status === 'running');

  return (
    <div className="flex-1 overflow-auto p-4 space-y-6 custom-scrollbar bg-bg/20">
      
      {/* Header Description */}
      <div className="flex justify-between items-end mb-2">
        <div>
          <h3 className="text-xs font-bold text-ink-bright uppercase tracking-widest">Colab Notebook Center</h3>
          <p className="text-[10px] text-ink/40">Generate and download self-contained Jupyter notebooks for cloud VRAM training</p>
        </div>
        <button
          onClick={fetchNotebooks}
          className="p-1 hover:bg-white/10 rounded text-accent flex items-center gap-1 text-[10px] font-bold uppercase transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh List
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Left Side: Generator Control */}
        <div className="lg:col-span-1 space-y-4">
          <Card title="Notebook Planner" subtitle="PLAN_BATCH_RUN">
            <form onSubmit={handleRegenerate} className="space-y-4">
              <div>
                <label className="text-[10px] uppercase font-bold text-ink/30 mb-1.5 flex items-center gap-1.5">
                  <Database className="w-3 h-3 text-accent" /> Subject Spec Glob
                </label>
                <input
                  type="text"
                  value={specGlob}
                  onChange={(e) => setSpecGlob(e.target.value)}
                  className="w-full bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none"
                  placeholder="e.g. subjects/*.json"
                  required
                />
                <p className="text-[8px] mt-1 text-ink/30">Paths to evaluate. Notebooks are generated for matching NPCs.</p>
              </div>

              <div>
                <label className="text-[10px] uppercase font-bold text-ink/30 mb-1.5 flex items-center gap-1.5">
                  <Sliders className="w-3 h-3 text-accent" /> Presets (comma-separated)
                </label>
                <input
                  type="text"
                  value={presets}
                  onChange={(e) => setPresets(e.target.value)}
                  className="w-full bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none"
                  placeholder="e.g. premium-3b,premium-8b"
                  required
                />
                <p className="text-[8px] mt-1 text-ink/30">Planner will match these configs against your local VRAM.</p>
              </div>

              <div>
                <label className="text-[10px] uppercase font-bold text-ink/30 mb-1.5 flex items-center gap-1.5">
                  <Cpu className="w-3 h-3 text-accent" /> Local GPU VRAM (GB)
                </label>
                <input
                  type="number"
                  step="0.1"
                  value={localVram}
                  onChange={(e) => setLocalVram(e.target.value)}
                  className="w-full bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none"
                  required
                />
                <p className="text-[8px] mt-1 text-ink/30">If preset needs more VRAM than this, planner routes to remote Colab.</p>
              </div>

              {runningPlanJob ? (
                <div className="p-3 bg-accent/5 border border-accent/20 rounded flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-accent animate-pulse" />
                    <span className="text-[10px] font-bold text-accent uppercase tracking-tighter">Generating Notebooks...</span>
                  </div>
                  <Badge variant="warning">Job Running</Badge>
                </div>
              ) : (
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="w-full py-2 bg-accent text-bg text-[10px] font-bold rounded uppercase tracking-wider hover:brightness-110 active:scale-[0.98] transition-all disabled:opacity-50"
                >
                  Regenerate Notebooks
                </button>
              )}
            </form>
          </Card>

          {/* Quick Info Card */}
          <Card title="Google Colab Setup" subtitle="GUIDE">
            <div className="space-y-3 text-[10px] text-ink/60">
              <div className="flex gap-2">
                <span className="font-bold text-accent shrink-0">1.</span>
                <p>Download the notebook matching your NPC and desired preset size (e.g. 8B).</p>
              </div>
              <div className="flex gap-2">
                <span className="font-bold text-accent shrink-0">2.</span>
                <p>Upload it to <a href="https://colab.research.google.com" target="_blank" rel="noreferrer" className="text-accent underline hover:brightness-110">Google Colab</a> (select a **T4 or L4 GPU** runtime).</p>
              </div>
              <div className="flex gap-2">
                <span className="font-bold text-accent shrink-0">3.</span>
                <p>Run the cells sequentially. Setup will mount your Google Drive to sync code and output adapters instantly!</p>
              </div>
            </div>
          </Card>
        </div>

        {/* Right Side: Notebook Grid */}
        <div className="lg:col-span-2 space-y-4">
          <Card title="Generated Notebooks" subtitle={`${notebooks.length} AVAILABLE`}>
            {error && (
              <div className="p-3 bg-danger/10 border border-danger/30 text-danger text-[11px] rounded">
                Error: {error}
              </div>
            )}

            {isLoading && notebooks.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 opacity-40 gap-2">
                <RefreshCw className="w-6 h-6 animate-spin text-accent" />
                <span className="text-[10px] uppercase font-mono tracking-widest">Scanning colab directory...</span>
              </div>
            ) : notebooks.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 opacity-30 gap-2">
                <BookOpen className="w-8 h-8 text-ink" />
                <span className="text-[10px] uppercase font-mono tracking-widest">No notebooks found. Run generation!</span>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-[11px]">
                  <thead>
                    <tr className="border-b border-line/45 text-ink/40 uppercase tracking-wider text-[9px] font-bold bg-header/20">
                      <th className="py-2.5 px-3">Notebook / NPC</th>
                      <th className="py-2.5 px-3">Target Preset</th>
                      <th className="py-2.5 px-3">Size</th>
                      <th className="py-2.5 px-3">Last Modified</th>
                      <th className="py-2.5 px-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {notebooks.map((nb) => (
                      <tr 
                        key={nb.name} 
                        className="border-b border-line/20 hover:bg-white/5 transition-colors group"
                      >
                        <td className="py-3 px-3">
                          <div className="font-semibold text-ink-bright truncate max-w-[200px]" title={nb.name}>
                            {nb.name.replace('__remote_colab.ipynb', '')}
                          </div>
                          <div className="text-[9px] text-ink/40 font-mono mt-0.5">
                            subjects/{nb.npcKey}.json
                          </div>
                        </td>
                        <td className="py-3 px-3">
                          <Badge variant={nb.preset.includes('8b') ? 'warning' : 'default'}>
                            {nb.preset.toUpperCase()}
                          </Badge>
                        </td>
                        <td className="py-3 px-3 text-ink/50 font-mono">
                          {nb.size}
                        </td>
                        <td className="py-3 px-3 text-ink/40 font-mono">
                          {new Date(nb.lastModified).toLocaleDateString()} {new Date(nb.lastModified).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </td>
                        <td className="py-3 px-3 text-right">
                          <div className="flex justify-end gap-2">
                            <button
                              onClick={() => handleDownload(nb.path, nb.name)}
                              className="px-2.5 py-1 border border-accent/30 bg-accent/5 text-accent rounded-sm hover:bg-accent/15 transition-all flex items-center gap-1.5 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
                              title="Download notebook file"
                            >
                              <Download className="w-3.5 h-3.5" />
                              <span>Download</span>
                            </button>
                            <a
                              href="https://colab.research.google.com"
                              target="_blank"
                              rel="noreferrer"
                              className="p-1 text-ink/40 hover:text-ink/80 rounded transition-colors"
                              title="Open Google Colab"
                            >
                              <ExternalLink className="w-3.5 h-3.5" />
                            </a>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>

      </div>

    </div>
  );
}
