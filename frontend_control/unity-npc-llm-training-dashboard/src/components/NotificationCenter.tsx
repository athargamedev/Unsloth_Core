import { useState, useEffect, useRef, useCallback } from 'react';
import { Bell, X, CheckCheck } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { cn } from '../lib/utils';
import { useAppStore } from '../stores/app-store';

const typeStyles: Record<string, string> = {
  info: 'border-l-accent bg-accent/8',
  success: 'border-l-success bg-success/8',
  warning: 'border-l-warning bg-warning/8',
  error: 'border-l-danger bg-danger/8',
};

const typeDots: Record<string, string> = {
  info: 'bg-accent',
  success: 'bg-success',
  warning: 'bg-warning',
  error: 'bg-danger',
};

export function NotificationCenter() {
  const [open, setOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  const toasts = useAppStore((s) => s.toasts);
  const dismissToast = useAppStore((s) => s.dismissToast);
  const markToastRead = useAppStore((s) => s.markToastRead);
  const clearAllToasts = useAppStore((s) => s.clearAllToasts);

  const unreadCount = toasts.filter((t) => !t.read).length;
  const displayToasts = [...toasts].reverse().slice(0, 50);

  // Click outside to close
  useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node) &&
        buttonRef.current &&
        !buttonRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open]);

  // Mark all visible toasts as read when opening
  const handleToggle = useCallback(() => {
    const next = !open;
    setOpen(next);
    if (next) {
      toasts.forEach((t) => {
        if (!t.read) markToastRead(t.id);
      });
    }
  }, [open, toasts, markToastRead]);

  const handleDismiss = useCallback(
    (id: string) => {
      dismissToast(id);
    },
    [dismissToast],
  );

  const handleClearAll = useCallback(() => {
    clearAllToasts();
    setOpen(false);
  }, [clearAllToasts]);

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        onClick={handleToggle}
        className="relative p-1.5 text-ink/40 hover:text-ink/80 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 rounded"
        aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ''}`}
      >
        <Bell className="w-4 h-4" />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 w-4 h-4 flex items-center justify-center rounded-full bg-danger text-[9px] font-bold text-white leading-none shadow-lg shadow-danger/30">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            ref={dropdownRef}
            initial={{ opacity: 0, y: -4, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.96 }}
            transition={{ duration: 0.12 }}
            className="absolute right-0 top-full mt-2 w-80 max-h-96 overflow-hidden bg-surface border border-line rounded-lg shadow-2xl shadow-black/50 z-[100] backdrop-blur-xl"
          >
            <div className="flex items-center justify-between px-3 py-2 border-b border-line bg-header/60">
              <span className="text-[10px] font-bold text-ink/60 uppercase tracking-widest">
                Notifications
              </span>
              <div className="flex items-center gap-2">
                {toasts.length > 0 && (
                  <button
                    onClick={handleClearAll}
                    className="flex items-center gap-1 text-[10px] font-bold text-ink/30 hover:text-ink/60 uppercase tracking-wider transition-colors"
                  >
                    <CheckCheck className="w-3 h-3" />
                    Clear all
                  </button>
                )}
              </div>
            </div>

            <div className="overflow-y-auto max-h-80 custom-scrollbar">
              {displayToasts.length > 0 ? (
                <AnimatePresence initial={false}>
                  {displayToasts.map((toast) => (
                    <ToastCard
                      toast={toast}
                      onDismiss={handleDismiss}
                    />
                  ))}
                </AnimatePresence>
              ) : (
                <div className="flex flex-col items-center justify-center py-10 px-4 text-center">
                  <Bell className="w-6 h-6 text-ink/20 mb-2" />
                  <span className="text-[11px] text-ink/30 font-medium">
                    No notifications
                  </span>
                  <span className="text-[10px] text-ink/20 mt-1">
                    Errors and status updates appear here
                  </span>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// Individual toast card with auto-dismiss
function ToastCard({
  toast,
  onDismiss,
}: {
  toast: { id: string; message: string; type: string };
  onDismiss: (id: string) => void;
}) {
  // Auto-dismiss after 8 seconds
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), 8000);
    return () => clearTimeout(timer);
  }, [toast.id, onDismiss]);

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: -8, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, x: 20, scale: 0.96 }}
      transition={{ duration: 0.15 }}
      className={cn(
        'flex items-start gap-2 px-3 py-2 border-l-2 border-b border-line/50 cursor-pointer hover:bg-white/[0.03] transition-colors group',
        typeStyles[toast.type] || typeStyles.info,
      )}
      onClick={() => onDismiss(toast.id)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onDismiss(toast.id);
        }
      }}
    >
      <div className={cn('w-1.5 h-1.5 rounded-full mt-1 shrink-0', typeDots[toast.type] || typeDots.info)} />
      <span className="text-[11px] text-ink/80 leading-relaxed flex-1 min-w-0 break-words">
        {toast.message}
      </span>
      <button
        onClick={(e) => {
          e.stopPropagation();
          onDismiss(toast.id);
        }}
        className="opacity-0 group-hover:opacity-100 text-ink/30 hover:text-ink/60 transition-all shrink-0"
        aria-label="Dismiss"
      >
        <X className="w-3 h-3" />
      </button>
    </motion.div>
  );
}
