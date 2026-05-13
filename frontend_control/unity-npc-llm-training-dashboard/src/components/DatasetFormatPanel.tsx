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

  const subject = subjects.find((s) => s.path === selectedSubject);
  const dataset = datasets.find((d) => d.id === selectedSubject);
  const techniqueInfo = dataset?.versions.find((v) => v.tag === selectedTechnique);

  const sampleRow = {
    text: "Hello, how can I help you?",
    messages: [
      { role: "system", content: "You are a helpful assistant." },
      { role: "user", content: "What is the capital of France?" },
      { role: "assistant", content: "Paris." },
    ],
  };

  return (
    <div className="p-4 space-y-6">
      <h3 className="text-lg font-bold text-ink-bright uppercase tracking-widest">Dataset Generation Overview</h3>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="text-[9px] uppercase font-bold text-ink/30 mb-1 block">Subject Spec</label>
          <select
            value={selectedSubject}
            onChange={(e) => {
              setSelectedSubject(e.target.value);
              setSelectedTechnique('');
            }}
            className="w-full bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none"
          >
            <option value="">Select subject…</option>
            {subjects.map((s) => (
              <option key={s.id} value={s.path}>
                {s.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-[9px] uppercase font-bold text-ink/30 mb-1 block">Technique</label>
          <select
            value={selectedTechnique}
            onChange={(e) => setSelectedTechnique(e.target.value)}
            disabled={!dataset}
            className="w-full bg-bg border border-line rounded px-3 py-2 text-xs font-mono focus:border-accent outline-none"
          >
            <option value="">Select technique…</option>
            {dataset?.versions.map((v) => (
              <option key={v.tag} value={v.tag}>
                {v.tag} ({v.entries} rows)
              </option>
            ))}
          </select>
        </div>
      </div>

      {selectedTechnique && (
        <div className="space-y-4">
          <h4 className="text-sm font-semibold text-ink/80">Format Details</h4>
          <p className="text-[11px] text-ink/60">
            Each line in the dataset JSONL file must be a valid JSON object. Two common schemas are supported:
          </p>
          <ul className="list-disc list-inside text-[11px] text-ink/70">
            <li><strong>Plain text</strong>: {`{ "text": "..." }`}</li>
            <li><strong>ChatML messages</strong>: {`{ "messages": [{"role":"system","content":"…"}, …] }`}</li>
          </ul>
          <pre className="bg-surface/30 p-3 rounded text-xs overflow-x-auto">
            {JSON.stringify(sampleRow, null, 2)}
          </pre>
          <p className="text-[11px] text-ink/50">
            Total rows for this technique: {techniqueInfo?.entries ?? 0}
          </p>
        </div>
      )}
    </div>
  );
};
