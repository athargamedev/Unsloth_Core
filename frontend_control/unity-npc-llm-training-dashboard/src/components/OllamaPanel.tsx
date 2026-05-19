import { useState, useEffect, useCallback } from 'react';
import {
  Wrench,
  RefreshCw,
  Server,
  Cpu,
  Zap,
  CheckCircle,
  XCircle,
  Loader2,
} from 'lucide-react';
import { Card } from './Card';
import { Badge } from './Badge';
import { cn } from '../lib/utils';
import { fetchJson } from '../api';
import type {
  OllamaStatus,
  OllamaModelList,
  OllamaApplyConfigPayload,
  OllamaApplyResult,
} from '../api';

type ApplyMode = 'restart' | 'no-restart';

export function OllamaPanel() {
  const [status, setStatus] = useState<OllamaStatus | null>(null);
  const [models, setModels] = useState<OllamaModelList | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [applying, setApplying] = useState(false);
  const [applyMessage, setApplyMessage] = useState<string | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [restarting, setRestarting] = useState(false);
  const [restartConfirm, setRestartConfirm] = useState(false);

  // Form state — initialised from status once loaded
  const [numParallel, setNumParallel] = useState(4);
  const [flashAttention, setFlashAttention] = useState(true);
  const [kvCacheType, setKvCacheType] = useState<'f16' | 'q8_0' | 'q4_0'>('f16');
  const [numGpu, setNumGpu] = useState(999);

  // Sync form fields when status loads
  useEffect(() => {
    if (!status) return;
    setNumParallel(parseInt(status.config.OLLAMA_NUM_PARALLEL, 10) || 4);
    setFlashAttention(status.config.OLLAMA_FLASH_ATTENTION === '1' || status.config.OLLAMA_FLASH_ATTENTION === 'true');
    setKvCacheType((status.config.OLLAMA_KV_CACHE_TYPE as 'f16' | 'q8_0' | 'q4_0') || 'f16');
    setNumGpu(parseInt(status.config.num_gpu, 10) || 999);
  }, [status]);

  const fetchStatus = useCallback(async () => {
    setStatusLoading(true);
    setError(null);
    try {
      const data = await fetchJson<OllamaStatus>('/api/ollama/status');
      setStatus(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setStatusLoading(false);
    }
  }, []);

  const fetchModels = useCallback(async () => {
    setModelsLoading(true);
    try {
      const data = await fetchJson<OllamaModelList>('/api/ollama/models');
      setModels(data);
    } catch {
      // Non-critical
    } finally {
      setModelsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    fetchModels();
  }, [fetchStatus, fetchModels]);

  const handleApply = async (mode: ApplyMode) => {
    setApplying(true);
    setApplyMessage(null);
    setApplyError(null);

    const payload: OllamaApplyConfigPayload = {
      OLLAMA_NUM_PARALLEL: numParallel,
      OLLAMA_FLASH_ATTENTION: flashAttention,
      OLLAMA_KV_CACHE_TYPE: kvCacheType,
      num_gpu: numGpu,
      restart: mode === 'restart',
    };

    try {
      const result = await fetch('/api/ollama/apply-config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data: OllamaApplyResult = await result.json();
      if (data.success) {
        setApplyMessage(data.message);
        if (data.needsRestart && mode === 'no-restart') {
          setApplyMessage(data.message + ' — restart Ollama for changes to take effect.');
        }
      } else {
        setApplyError(data.message);
      }
    } catch (err: any) {
      setApplyError(err.message);
    } finally {
      setApplying(false);
    }
  };

  const handleRestart = async () => {
    if (!restartConfirm) {
      setRestartConfirm(true);
      setTimeout(() => setRestartConfirm(false), 4000);
      return;
    }
    setRestarting(true);
    setApplyMessage(null);
    setApplyError(null);
    try {
      const result = await fetch('/api/ollama/restart', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await result.json();
      if (data.success) {
        setApplyMessage('Ollama service restarted successfully.');
        setTimeout(() => {
          fetchStatus();
          fetchModels();
        }, 3000);
      } else {
        setApplyError(data.message || 'Restart failed');
      }
    } catch (err: any) {
      setApplyError(err.message);
    } finally {
      setRestarting(false);
      setRestartConfirm(false);
    }
  };

  const formatSize = (size: string) => {
    const num = parseFloat(size);
    if (Number.isNaN(num)) return size;
    if (num >= 1e9) return `${(num / 1e9).toFixed(1)} GB`;
    if (num >= 1e6) return `${(num / 1e6).toFixed(1)} MB`;
    return size;
  };

  return (
    <div className="flex-1 flex flex-col overflow-auto p-4 space-y-4 custom-scrollbar">
      {/* Service Status Card */}
      <Card title="Service Status">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {statusLoading ? (
              <div className="flex items-center gap-2 text-ink/40">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span className="text-[12px]">Checking service…</span>
              </div>
            ) : status?.running ? (
              <div className="flex items-center gap-2">
                <CheckCircle className="w-5 h-5 text-success" />
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-[12px] font-bold text-success uppercase tracking-wider">Running</span>
                    {status.pid && (
                      <span className="text-[10px] font-mono text-ink/40">PID {status.pid}</span>
                    )}
                  </div>
                  {status.activeModel && (
                    <div className="text-[10px] font-mono text-ink/50 mt-0.5">
                      Active model: <span className="text-accent">{status.activeModel}</span>
                      {status.gpuLayers !== null && (
                        <span className="text-ink/40"> · {status.gpuLayers} GPU layers</span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <XCircle className="w-5 h-5 text-danger" />
                <div>
                  <span className="text-[12px] font-bold text-danger uppercase tracking-wider">Stopped</span>
                  <div className="text-[10px] font-mono text-ink/40 mt-0.5">Ollama service is not running</div>
                </div>
              </div>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => { fetchStatus(); fetchModels(); }}
              className="flex items-center gap-1 px-2 py-1 border border-line rounded text-[10px] font-bold text-ink/50 hover:text-ink transition-colors"
              title="Refresh status"
            >
              <RefreshCw className="w-3 h-3" />
              Refresh
            </button>
            <button
              onClick={handleRestart}
              disabled={restarting}
              className={cn(
                "flex items-center gap-1 px-3 py-1 rounded text-[10px] font-bold uppercase tracking-wider transition-all",
                restartConfirm
                  ? "bg-danger text-white border border-danger animate-pulse"
                  : "bg-surface border border-line text-ink/60 hover:text-ink",
              )}
            >
              <RefreshCw className={cn("w-3 h-3", restarting && "animate-spin")} />
              {restarting ? 'Restarting…' : restartConfirm ? 'Confirm Restart' : 'Restart Ollama'}
            </button>
          </div>
        </div>
        {error && <div className="text-[10px] text-danger mt-1">{error}</div>}
      </Card>

      {/* Performance Tuning Section */}
      <Card title="Performance Tuning">
        <div className="text-[10px] text-ink/40 mb-4">
          Environment variables applied via <code className="text-accent">/etc/systemd/system/ollama.service.d/override.conf</code>. Changes require a service restart.
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* OLLAMA_NUM_PARALLEL */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-[11px] font-bold text-ink/70 uppercase tracking-wider flex items-center gap-1.5">
                <Server className="w-3 h-3 text-accent" />
                OLLAMA_NUM_PARALLEL
              </label>
              <span className="text-[12px] font-mono font-bold text-accent">{numParallel}</span>
            </div>
            <input
              type="range"
              min={1}
              max={8}
              step={1}
              value={numParallel}
              onChange={(e) => setNumParallel(Number(e.target.value))}
              className="w-full h-1.5 bg-line rounded-full appearance-none cursor-pointer accent-accent"
            />
            <div className="flex justify-between text-[9px] text-ink/30 font-mono">
              <span>1</span>
              <span>4</span>
              <span>8</span>
            </div>
            <p className="text-[10px] text-ink/40 leading-relaxed">
              Concurrent request slots — higher = faster batch evaluation, more VRAM pressure.
            </p>
          </div>

          {/* OLLAMA_FLASH_ATTENTION */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-[11px] font-bold text-ink/70 uppercase tracking-wider flex items-center gap-1.5">
                <Zap className="w-3 h-3 text-accent" />
                OLLAMA_FLASH_ATTENTION
              </label>
              <button
                onClick={() => setFlashAttention(!flashAttention)}
                className={cn(
                  "relative w-10 h-5 rounded-full transition-colors border",
                  flashAttention ? "bg-accent/30 border-accent" : "bg-line border-line",
                )}
              >
                <div
                  className={cn(
                    "absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform shadow",
                    flashAttention ? "translate-x-5" : "translate-x-0.5",
                  )}
                />
              </button>
            </div>
            <p className="text-[10px] text-ink/40 leading-relaxed">
              Flash attention — free speed and memory reduction (requires restart).
            </p>
          </div>

          {/* OLLAMA_KV_CACHE_TYPE */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-[11px] font-bold text-ink/70 uppercase tracking-wider flex items-center gap-1.5">
                <Cpu className="w-3 h-3 text-accent" />
                OLLAMA_KV_CACHE_TYPE
              </label>
              <select
                value={kvCacheType}
                onChange={(e) => setKvCacheType(e.target.value as 'f16' | 'q8_0' | 'q4_0')}
                className="bg-bg border border-line rounded px-2 py-1 text-[11px] font-mono text-ink/80 focus:outline-none focus:border-accent"
              >
                <option value="f16">f16</option>
                <option value="q8_0">q8_0</option>
                <option value="q4_0">q4_0</option>
              </select>
            </div>
            <p className="text-[10px] text-ink/40 leading-relaxed">
              KV cache quantization — q8_0 halves memory with near-zero quality loss.
            </p>
          </div>

          {/* GPU Offloading (num_gpu) */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-[11px] font-bold text-ink/70 uppercase tracking-wider flex items-center gap-1.5">
                <Cpu className="w-3 h-3 text-accent" />
                GPU Offloading (num_gpu)
              </label>
              <input
                type="number"
                min={1}
                max={999}
                value={numGpu}
                onChange={(e) => setNumGpu(Math.max(1, Math.min(999, Number(e.target.value) || 1)))}
                className="w-20 bg-bg border border-line rounded px-2 py-1 text-[11px] font-mono text-ink/80 text-right focus:outline-none focus:border-accent"
              />
            </div>
            <p className="text-[10px] text-ink/40 leading-relaxed">
              GPU layers to offload — 999 = all layers to GPU, 0 = CPU only.
            </p>
          </div>
        </div>
      </Card>

      {/* Apply Buttons */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => handleApply('restart')}
          disabled={applying}
          className="flex items-center gap-2 px-4 py-2 bg-accent text-bg text-[11px] font-bold rounded-sm uppercase tracking-wider hover:brightness-110 transition-all active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {applying ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Zap className="w-3.5 h-3.5" />
          )}
          Apply & Restart Ollama
        </button>
        <button
          onClick={() => handleApply('no-restart')}
          disabled={applying}
          className="flex items-center gap-2 px-4 py-2 bg-surface border border-line text-ink/60 text-[11px] font-bold rounded-sm uppercase tracking-wider hover:text-ink transition-all active:scale-95 disabled:opacity-40"
        >
          Apply (No Restart)
        </button>
      </div>

      {/* Apply status messages */}
      {applyMessage && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-sm bg-success/10 border border-success/30 text-[11px] text-success">
          <CheckCircle className="w-3.5 h-3.5 shrink-0" />
          {applyMessage}
        </div>
      )}
      {applyError && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-sm bg-danger/10 border border-danger/30 text-[11px] text-danger">
          <XCircle className="w-3.5 h-3.5 shrink-0" />
          {applyError}
        </div>
      )}

      {/* Model Inventory */}
      <Card title="Model Inventory" subtitle={models?.models ? `${models.models.length} models` : undefined}>
        {modelsLoading ? (
          <div className="flex items-center justify-center py-8 text-ink/40">
            <Loader2 className="w-4 h-4 animate-spin mr-2" />
            <span className="text-[12px]">Loading models…</span>
          </div>
        ) : models?.models && models.models.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-line">
                  <th className="text-left py-2 pr-4 text-[9px] font-bold text-ink/40 uppercase tracking-wider">Name</th>
                  <th className="text-left py-2 pr-4 text-[9px] font-bold text-ink/40 uppercase tracking-wider">Parameters</th>
                  <th className="text-left py-2 pr-4 text-[9px] font-bold text-ink/40 uppercase tracking-wider">Quantization</th>
                  <th className="text-left py-2 pr-4 text-[9px] font-bold text-ink/40 uppercase tracking-wider">Family</th>
                  <th className="text-right py-2 text-[9px] font-bold text-ink/40 uppercase tracking-wider">Size</th>
                </tr>
              </thead>
              <tbody>
                {models.models.map((model) => (
                  <tr key={model.name} className="border-b border-line/40 hover:bg-white/[0.02] transition-colors">
                    <td className="py-2 pr-4 font-mono text-ink-bright truncate max-w-[200px]" title={model.name}>
                      {model.name}
                    </td>
                    <td className="py-2 pr-4 text-ink/60">
                      {model.details?.parameter_size || '—'}
                    </td>
                    <td className="py-2 pr-4">
                      {model.details?.quantization_level ? (
                        <Badge variant="default">{model.details.quantization_level}</Badge>
                      ) : (
                        <span className="text-ink/30">—</span>
                      )}
                    </td>
                    <td className="py-2 pr-4 text-ink/60">
                      {model.details?.family || '—'}
                    </td>
                    <td className="py-2 text-right font-mono text-ink/50">
                      {formatSize(model.size)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-8 text-ink/30 gap-2">
            <Server className="w-8 h-8 opacity-30" />
            <span className="text-[11px]">No models found</span>
            <span className="text-[10px]">Pull a model with <code className="text-accent">ollama pull &lt;model&gt;</code></span>
          </div>
        )}
      </Card>
    </div>
  );
}
