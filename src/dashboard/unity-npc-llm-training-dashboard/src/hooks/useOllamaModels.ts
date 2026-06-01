import { useState, useEffect, useCallback } from 'react';

export interface OllamaModel {
  name: string;
  size: string;
  modified: string;
  details?: {
    parameter_size?: string;
    quantization_level?: string;
    family?: string;
  };
}

interface OllamaModelsState {
  models: OllamaModel[];
  loading: boolean;
  error: string | null;
}

// Module-level cache so all hook instances share one request
let _cache: OllamaModel[] | null = null;
let _cacheTime = 0;
const CACHE_TTL_MS = 30_000;
let _inFlight: Promise<OllamaModel[]> | null = null;

async function fetchModels(): Promise<OllamaModel[]> {
  if (_cache && Date.now() - _cacheTime < CACHE_TTL_MS) return _cache;
  if (_inFlight) return _inFlight;

  _inFlight = fetch('/api/ollama/models')
    .then(async (res) => {
      if (!res.ok) return [];
      const data = (await res.json()) as { models?: OllamaModel[] };
      _cache = data.models ?? [];
      _cacheTime = Date.now();
      return _cache;
    })
    .catch(() => {
      _cache = [];
      _cacheTime = Date.now();
      return [];
    })
    .finally(() => {
      _inFlight = null;
    });

  return _inFlight;
}

/** Returns the list of models available in local Ollama. */
export function useOllamaModels(): OllamaModelsState & { refetch: () => void } {
  const [state, setState] = useState<OllamaModelsState>({
    models: _cache ?? [],
    loading: !_cache,
    error: null,
  });

  const load = useCallback(() => {
    setState((s) => ({ ...s, loading: true }));
    fetchModels()
      .then((models) => setState({ models, loading: false, error: null }))
      .catch(() => setState({ models: [], loading: false, error: 'Failed to load Ollama models' }));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return { ...state, refetch: load };
}

/** Invalidate the global Ollama model cache. */
export function invalidateOllamaModelsCache() {
  _cache = null;
  _cacheTime = 0;
}
