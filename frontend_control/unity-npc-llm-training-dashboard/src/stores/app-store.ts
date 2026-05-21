import { create } from 'zustand';
import type { TrainingConfig } from '../api';

// --- Persistent defaults ---

const DEFAULT_TRAINING_CONFIG: TrainingConfig = {
  spec: 'subjects/NPC_specs/history_guide.json',
  preset: 'fast-3b',
  technique: 'template',
  baseModel: 'unsloth/Llama-3.2-3B-Instruct-bnb-4bit',
  learningRate: '2e-4',
  scheduler: 'cosine',
  batchSize: 1,
  epochs: 3,
  rank: 16,
  alpha: 32,
  wandb: false,
};

export interface UIState {
  // Active tab
  activeTab: string;
  setActiveTab: (tab: string) => void;

  // Selected jobs
  selectedJobId: string | null;
  setSelectedJobId: (id: string | null) => void;
  selectedJobIds: string[];
  addSelectedJobId: (id: string) => void;
  removeSelectedJobId: (id: string) => void;
  clearSelectedJobIds: () => void;

  // Active filters
  jobTypeFilter: string[];
  toggleJobTypeFilter: (type: string) => void;
  activeFilter: 'all' | 'running' | 'completed' | 'failed';
  setActiveFilter: (filter: 'all' | 'running' | 'completed' | 'failed') => void;

  // Dataset view
  datasetViewNpc: string;
  setDatasetViewNpc: (npc: string) => void;
  datasetViewTechnique: string;
  setDatasetViewTechnique: (technique: string) => void;

  // Training config (persisted UI state)
  trainingConfig: TrainingConfig;
  updateTrainingConfig: (config: Partial<TrainingConfig>) => void;

  // UI flags
  commandModalOpen: boolean;
  setCommandModalOpen: (open: boolean) => void;
  selectedCommand: string | null;
  setSelectedCommand: (cmd: string | null) => void;
  commandPayload: Record<string, unknown>;
  setCommandPayload: (payload: Record<string, unknown>) => void;

  // Toast/notification system
  toasts: Array<{ id: string; message: string; type: 'info' | 'success' | 'warning' | 'error'; timestamp: number; read: boolean }>;
  addToast: (message: string, type?: 'info' | 'success' | 'warning' | 'error') => void;
  dismissToast: (id: string) => void;
  markToastRead: (id: string) => void;
  clearAllToasts: () => void;

  // Recent searches (persisted to localStorage)
  recentSearches: string[];
  addRecentSearch: (query: string) => void;
  clearRecentSearches: () => void;

  // Error
  uiError: string | null;
  setUiError: (error: string | null) => void;
}

export const useAppStore = create<UIState>((set, get) => ({
  // ── Active Tab ──

  activeTab: 'overview',
  setActiveTab: (tab: string) => set({ activeTab: tab }),

  // ── Selected Jobs ──

  selectedJobId: null,
  setSelectedJobId: (id: string | null) => set({ selectedJobId: id }),

  selectedJobIds: [],
  addSelectedJobId: (id: string) => {
    const { selectedJobIds } = get();
    if (!selectedJobIds.includes(id)) {
      set({ selectedJobIds: [...selectedJobIds, id] });
    }
  },
  removeSelectedJobId: (id: string) => {
    set({ selectedJobIds: get().selectedJobIds.filter((jid) => jid !== id) });
  },
  clearSelectedJobIds: () => set({ selectedJobIds: [] }),

  // ── Filters ──

  jobTypeFilter: ['Training', 'Dataset', 'Export', 'Evaluation'],
  toggleJobTypeFilter: (type: string) => {
    const { jobTypeFilter } = get();
    set({
      jobTypeFilter: jobTypeFilter.includes(type)
        ? jobTypeFilter.filter((t) => t !== type)
        : [...jobTypeFilter, type],
    });
  },

  activeFilter: 'all',
  setActiveFilter: (filter: 'all' | 'running' | 'completed' | 'failed') =>
    set({ activeFilter: filter }),

  // ── Dataset View ──

  datasetViewNpc: '',
  setDatasetViewNpc: (npc: string) => set({ datasetViewNpc: npc }),
  datasetViewTechnique: '',
  setDatasetViewTechnique: (technique: string) => set({ datasetViewTechnique: technique }),

  // ── Training Config ──

  trainingConfig: { ...DEFAULT_TRAINING_CONFIG },
  updateTrainingConfig: (config: Partial<TrainingConfig>) => {
    set({ trainingConfig: { ...get().trainingConfig, ...config } });
  },

  // ── UI Flags / Command Modal ──

  commandModalOpen: false,
  setCommandModalOpen: (open: boolean) => set({ commandModalOpen: open }),

  selectedCommand: null,
  setSelectedCommand: (cmd: string | null) => set({ selectedCommand: cmd }),

  commandPayload: {},
  setCommandPayload: (payload: Record<string, unknown>) =>
    set({ commandPayload: payload }),

  // ── Toast / Notification System ──

  toasts: [],
  addToast: (message: string, type: 'info' | 'success' | 'warning' | 'error' = 'info') => {
    const toast = {
      id: crypto.randomUUID(),
      message,
      type,
      timestamp: Date.now(),
      read: false,
    };
    set({ toasts: [...get().toasts, toast] });
  },
  dismissToast: (id: string) => {
    set({ toasts: get().toasts.filter((t) => t.id !== id) });
  },
  markToastRead: (id: string) => {
    set({ toasts: get().toasts.map((t) => (t.id === id ? { ...t, read: true } : t)) });
  },
  clearAllToasts: () => {
    set({ toasts: [] });
  },

  // ── Recent Searches (persisted to localStorage) ──

  recentSearches: (() => {
    try {
      return JSON.parse(localStorage.getItem('recentSearches') || '[]');
    } catch {
      return [];
    }
  })(),
  addRecentSearch: (query: string) => {
    const { recentSearches } = get();
    const updated = [query, ...recentSearches.filter((s) => s !== query)].slice(0, 10);
    set({ recentSearches: updated });
    try {
      localStorage.setItem('recentSearches', JSON.stringify(updated));
    } catch { /* localStorage may be unavailable */ }
  },
  clearRecentSearches: () => {
    set({ recentSearches: [] });
    try {
      localStorage.removeItem('recentSearches');
    } catch { /* localStorage may be unavailable */ }
  },

  // ── Error State ──

  uiError: null,
  setUiError: (error: string | null) => set({ uiError: error }),
}));
