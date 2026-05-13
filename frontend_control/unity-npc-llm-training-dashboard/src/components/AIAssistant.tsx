import { useState, useEffect } from 'react';
import { Sparkles } from 'lucide-react';
import { fetchOptionalJson, type AssistantMessage } from '../api';

export const AIAssistant = () => {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<AssistantMessage[]>([
    {
      role: 'assistant',
      content: `Welcome to Unity NPC Core Assistant. How can I help with your workflow?`,
    },
  ]);
  const [suggestions, setSuggestions] = useState<string[]>([]);

  useEffect(() => {
    fetchOptionalJson<string[]>('/api/suggestions').then((data) => {
      if (data) setSuggestions(data);
    });
  }, []);

  const askAI = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || loading) return;

    const userMsg = query;
    setQuery('');
    setMessages((prev) => [...prev, { role: 'user', content: userMsg }]);
    setLoading(true);

    try {
      const response = await fetch('/api/assistant', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMsg,
          history: messages,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.error || 'Assistant request failed.');
      }

      setMessages((prev) => [...prev, { role: 'assistant', content: payload.content || 'Error processing request.' }]);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Connection failed.';
      setMessages((prev) => [...prev, { role: 'assistant', content: `Error: ${message}` }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <aside className="w-64 border-r border-line bg-surface flex flex-col overflow-hidden">
      <div className="p-3 border-b border-line bg-panel">
        <h2 className="text-[11px] font-bold text-ink-bright uppercase tracking-wider mb-2">Workflow Assistant</h2>
        <div className="p-2 bg-accent/5 border border-accent/20 rounded text-[11px] leading-relaxed italic text-accent animate-in fade-in">
          {messages[messages.length - 1].content}
        </div>
      </div>

      <div className="flex-1 overflow-hidden p-3 flex flex-col gap-3">
        {/* Dynamic Context Hint */}
        <div className="flex flex-col gap-1">
          <span className="text-[9px] uppercase font-bold text-accent tracking-widest flex items-center gap-1">
            <Sparkles className="w-2 h-2" />
            Live Suggestions
          </span>
          <div className="p-2 border border-accent/20 rounded bg-accent/5 text-[10px] text-accent/80 italic leading-snug">
            {suggestions.length > 0 ? suggestions[Math.floor(Math.random() * suggestions.length)] : 'System suggests checking Rank size for QuestGiver LoRA if loss plateau persists.'}
          </div>
        </div>

        <div className="flex flex-col gap-1">
          <span className="text-[9px] uppercase font-bold text-ink/40 tracking-widest">Active Documentation</span>
          <div className="p-2 border border-line rounded bg-bg text-[10px] text-ink/60 cursor-help hover:border-accent/40 transition-colors">
            • dataset_formatting.md<br />
            • unity_npc_protocol.pdf<br />
            • dialogue_states_v4.json
          </div>
        </div>

        <div className="mt-auto">
          <form onSubmit={askAI}>
            <textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); askAI(e); } }}
              className="w-full h-24 bg-bg border border-line rounded p-2 text-[11px] focus:outline-none focus:border-accent transition-colors resize-none mb-1 shadow-inner"
              placeholder={loading ? 'Assistant is thinking...' : 'Ask assistant about workflow...'}
            />
            {loading && <div className="text-[9px] text-accent font-bold animate-pulse">PROCESSING_REQUEST...</div>}
          </form>
        </div>
      </div>
    </aside>
  );
};
