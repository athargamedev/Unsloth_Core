import { useState, useEffect, useRef } from 'react';
import { Sparkles, BookOpen, Send, User, Bot, Command, Power, PowerOff } from 'lucide-react';
import { fetchOptionalJson, type AssistantMessage } from '../api';
import ReactMarkdown from 'react-markdown';

export const AIAssistant = () => {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<AssistantMessage[]>([
    {
      role: 'assistant',
      content: `Welcome to **Unity NPC Core Assistant**. I can help you with:
- Generating synthetic datasets
- Choosing the right training presets
- Exporting models to GGUF
- Troubleshooting pipeline errors

How can I help with your workflow today?`,
    },
  ]);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [docs, setDocs] = useState<string[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchOptionalJson<string[]>('/api/suggestions').then((data) => {
      if (data) setSuggestions(data);
    });
    fetchOptionalJson<string[]>('/api/docs').then((data) => {
      if (data && data.length > 0) setDocs(data);
    });
  }, []);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const askAI = async (e?: React.FormEvent) => {
    e?.preventDefault();
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
      setMessages((prev) => [...prev, { role: 'assistant', content: `**Error:** ${message}` }]);
    } finally {
      setLoading(false);
    }
  };

  const defaultSuggestion = 'Try checking Rank size for QuestGiver LoRA if loss plateau persists.';

  const handleUnloadModel = async () => {
    try {
      await fetch('/api/assistant/unload', { method: 'POST' });
      setMessages((prev) => [...prev, { role: 'assistant', content: '_Model unloaded from GPU._' }]);
    } catch {}
  };

  const handleLoadModel = async () => {
    try {
      setMessages((prev) => [...prev, { role: 'assistant', content: '_Loading model into GPU..._' }]);
      await fetch('/api/assistant/load', { method: 'POST' });
    } catch {}
  };

  return (
    <aside className="w-80 border-r border-line bg-surface flex flex-col overflow-hidden shadow-2xl">
      {/* Header */}
      <div className="p-4 border-b border-line bg-panel/50 backdrop-blur-md flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-accent animate-pulse" />
          <h2 className="text-[11px] font-bold text-ink-bright uppercase tracking-widest">Workflow Assistant</h2>
        </div>
        <div className="flex gap-2">
          <button onClick={handleLoadModel} title="Load Model into GPU" className="p-1 hover:bg-white/10 rounded text-accent">
            <Power className="w-3 h-3" />
          </button>
          <button onClick={handleUnloadModel} title="Unload Model from GPU" className="p-1 hover:bg-white/10 rounded text-danger">
            <PowerOff className="w-3 h-3" />
          </button>
        </div>
      </div>

      {/* Messages Area */}
      <div 
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-4 space-y-6 scroll-smooth"
      >
        {messages.map((msg, i) => (
          <div key={i} className={`flex flex-col gap-2 ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
            <div className="flex items-center gap-2 mb-1">
              {msg.role === 'user' ? (
                <>
                  <span className="text-[9px] font-bold text-ink/40 uppercase tracking-tighter">You</span>
                  <User className="w-3 h-3 text-ink/40" />
                </>
              ) : (
                <>
                  <Bot className="w-3 h-3 text-accent" />
                  <span className="text-[9px] font-bold text-accent uppercase tracking-tighter">Assistant</span>
                </>
              )}
            </div>
            <div className={`max-w-[90%] p-3 rounded-2xl text-[11px] leading-relaxed shadow-sm ${
              msg.role === 'user' 
                ? 'bg-accent text-white rounded-tr-none' 
                : 'bg-bg border border-line rounded-tl-none prose prose-invert prose-xs'
            }`}>
              {msg.role === 'assistant' ? (
                <ReactMarkdown 
                  components={{
                    code({ className, children, ...props }) {
                      const match = /language-(\w+)/.exec(className || '');
                      const content = String(children).replace(/\n$/, '');
                      const isInline = !content.includes('\n');
                      const isCommand = content.includes('./ucore');
                      
                      if (!isInline && isCommand) {
                        return (
                          <div className="my-2 border border-accent/30 rounded bg-black/40 overflow-hidden">
                            <div className="flex items-center justify-between px-2 py-1 bg-accent/10 border-b border-accent/20">
                              <span className="text-[8px] font-bold text-accent flex items-center gap-1">
                                <Command className="w-2 h-2" />
                                ACTIONABLE COMMAND
                              </span>
                            </div>
                            <code className="block p-2 text-accent-bright font-mono whitespace-pre-wrap">
                              {content}
                            </code>
                          </div>
                        );
                      }
                      return (
                        <code className={`${className} bg-bg-deep px-1 rounded text-accent`} {...props}>
                          {children}
                        </code>
                      );
                    }
                  }}
                >
                  {msg.content}
                </ReactMarkdown>
              ) : (
                msg.content
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex items-center gap-2 text-accent animate-pulse">
            <Bot className="w-3 h-3" />
            <div className="flex gap-1">
              <span className="w-1 h-1 rounded-full bg-accent animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-1 h-1 rounded-full bg-accent animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-1 h-1 rounded-full bg-accent animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        )}
      </div>

      {/* Footer / Input */}
      <div className="p-4 bg-panel/30 border-t border-line">
        {/* Context Hints */}
        {!loading && messages.length < 3 && (
          <div className="mb-4 space-y-2">
            <div className="text-[9px] font-bold text-ink/30 uppercase tracking-widest mb-1">Quick Actions</div>
            <div className="flex flex-wrap gap-2">
              <button 
                onClick={() => { setQuery('How do I run a smoke test?'); askAI(); }}
                className="text-[10px] bg-bg border border-line px-2 py-1 rounded hover:border-accent transition-colors"
              >
                Smoke Test Help
              </button>
              <button 
                onClick={() => { setQuery('Explain the 4-stage pipeline'); askAI(); }}
                className="text-[10px] bg-bg border border-line px-2 py-1 rounded hover:border-accent transition-colors"
              >
                Pipeline Overview
              </button>
            </div>
          </div>
        )}

        <form onSubmit={askAI} className="relative">
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); askAI(); } }}
            className="w-full h-20 bg-bg border border-line rounded-xl p-3 text-[11px] focus:outline-none focus:border-accent transition-all resize-none shadow-inner pr-10"
            placeholder="Ask assistant about workflow..."
          />
          <button 
            type="submit"
            disabled={!query.trim() || loading}
            className="absolute right-3 bottom-3 p-1.5 bg-accent rounded-lg text-white disabled:opacity-30 transition-opacity"
          >
            <Send className="w-3 h-3" />
          </button>
        </form>
      </div>
    </aside>
  );
};
