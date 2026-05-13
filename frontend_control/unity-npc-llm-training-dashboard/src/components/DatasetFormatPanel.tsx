import React from 'react';
import { cn } from '../lib/utils';

interface VersionInfo {
  tag: string;
  entries: number;
  val_entries?: number;
}

interface DatasetInfo {
  id: string;
  name: string;
  versions: VersionInfo[];
}

interface SubjectInfo {
  id: string;
  name: string;
  path: string;
}

interface DatasetFormatPanelProps {
  subjects: SubjectInfo[];
  datasets: DatasetInfo[];
  trainingConfig: any; // reuse trainingConfig shape
}

export const DatasetFormatPanel = ({ subjects, datasets, trainingConfig }: DatasetFormatPanelProps) => {
  const [selectedSubject, setSelectedSubject] = React.useState<string>('');
  const [selectedTechnique, setSelectedTechnique] = React.useState<string>('');

  const subjectSpec = subjects.find((s) => s.path === selectedSubject);
  const dataset = datasets.find((d) => d.id === selectedSubject);
  const techniqueInfo = dataset?.versions.find((v) => v.tag === selectedTechnique);

  const sampleRow = {
    text: "How do I use a pipette correctly?",
    messages: [
      { role: "system", content: "You are a professional chemistry instructor..." },
      { role: "user", content: "How do I use a pipette correctly?" },
      { role: "assistant", content: "Hold it vertically and use the bulb to draw liquid just above the mark..." },
    ],
  };

  return (
    <div className="p-4 space-y-6 flex-1 overflow-auto custom-scrollbar">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-bold text-ink-bright uppercase tracking-widest">Generation Logic & Parameters</h3>
        <div className="flex gap-2">
          <span className="px-2 py-0.5 bg-accent/10 border border-accent/30 text-accent text-[9px] font-bold rounded uppercase">Logic: Synthetic_v3</span>
          <span className="px-2 py-0.5 bg-success/10 border border-success/30 text-success text-[9px] font-bold rounded uppercase">Output: ChatML</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Left: Configuration Overview */}
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-[9px] uppercase font-bold text-ink/30 mb-1 block tracking-wider">Subject Spec</label>
              <select
                value={selectedSubject}
                onChange={(e) => {
                  setSelectedSubject(e.target.value);
                  setSelectedTechnique('');
                }}
                className="w-full bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none transition-all"
              >
                <option value="">Select subjectSpec…</option>
                {subjects.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-[9px] uppercase font-bold text-ink/30 mb-1 block tracking-wider">Active Technique</label>
              <select
                value={selectedTechnique}
                onChange={(e) => setSelectedTechnique(e.target.value)}
                disabled={!dataset}
                className="w-full bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none transition-all"
              >
                <option value="">Select technique…</option>
                {dataset?.versions.map((v) => (
                  <option key={v.tag} value={v.tag}>
                    {v.tag.toUpperCase()}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="p-4 bg-surface/30 border border-line rounded-lg space-y-3">
            <h4 className="text-[10px] font-bold text-ink-bright uppercase tracking-widest border-b border-line/50 pb-2">Pipeline Logic</h4>
            <div className="grid grid-cols-2 gap-y-3 gap-x-6">
              <div className="flex flex-col">
                <span className="text-[8px] uppercase text-ink/40 font-bold">Generation Strategy</span>
                <span className="text-[11px] font-mono text-accent">
                  {selectedTechnique === 'notebooklm' ? 'External Import' : selectedTechnique === 'template' ? 'Heuristic Template' : 'LLM Synthesis'}
                </span>
              </div>
              <div className="flex flex-col">
                <span className="text-[8px] uppercase text-ink/40 font-bold">Split Strategy</span>
                <span className="text-[11px] font-mono">Stratified (12% Val)</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[8px] uppercase text-ink/40 font-bold">Total Entries</span>
                <span className="text-[11px] font-mono text-success font-bold">{techniqueInfo?.entries || '--'}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[8px] uppercase text-ink/40 font-bold">Validation Set</span>
                <span className="text-[11px] font-mono text-warning font-bold">{techniqueInfo?.val_entries || Math.floor((techniqueInfo?.entries || 0) * 0.12) || '--'}</span>
              </div>
            </div>
          </div>

          <div className="p-4 bg-surface/30 border border-line rounded-lg space-y-3">
            <h4 className="text-[10px] font-bold text-ink-bright uppercase tracking-widest border-b border-line/50 pb-2">Hyperparameters</h4>
            <div className="grid grid-cols-2 gap-y-3 gap-x-6">
              <div className="flex flex-col">
                <span className="text-[8px] uppercase text-ink/40 font-bold">Temperature</span>
                <span className="text-[11px] font-mono">0.8</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[8px] uppercase text-ink/40 font-bold">Multi-Turn Ratio</span>
                <span className="text-[11px] font-mono">0.2</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[8px] uppercase text-ink/40 font-bold">Seed</span>
                <span className="text-[11px] font-mono">42</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[8px] uppercase text-ink/40 font-bold">Format</span>
                <span className="text-[11px] font-mono text-accent">JSONL / ChatML</span>
              </div>
            </div>
          </div>
        </div>

        {/* Right: Format Schema & Preview */}
        <div className="space-y-4">
          <div className="p-4 bg-header/40 border border-line rounded-lg flex-1">
            <div className="flex justify-between items-center mb-3">
              <h4 className="text-[10px] font-bold text-ink-bright uppercase tracking-widest">Expected JSON Schema</h4>
              <span className="text-[9px] font-mono text-ink/40">v2.0_STABLE</span>
            </div>
            <pre className="text-[10px] font-mono bg-bg/50 p-4 rounded border border-line/50 text-accent overflow-auto max-h-[350px] custom-scrollbar leading-relaxed">
              {`{
  "messages": [
    { "role": "system", "content": "..." },
    { "role": "user", "content": "..." },
    { "role": "assistant", "content": "..." }
  ],
  "metadata": {
    "npc_key": "${selectedSubject || '... '}",
    "technique": "${selectedTechnique || '... '}",
    "source": "ollama:llama3.1",
    "concept": "concept_name"
  }
}`}
            </pre>
            <div className="mt-4 p-3 bg-accent/5 border border-accent/20 rounded text-[10px] text-ink/60 italic">
              Note: Unsloth SFTTrainer expects either a 'text' field or a 'messages' list. Our pipeline standardizes on the 'messages' format for multi-turn consistency.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
