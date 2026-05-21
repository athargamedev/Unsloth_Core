import { useEffect } from 'react';

function isInputFocused(): boolean {
  const el = document.activeElement;
  return (
    el instanceof HTMLInputElement ||
    el instanceof HTMLTextAreaElement ||
    el instanceof HTMLSelectElement
  );
}

export function useKeyboardShortcuts() {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Ctrl+K / Cmd+K: Open global search
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent('open-search'));
      }

      // Ctrl+Shift+S: Stop all jobs (when no input is focused)
      if ((e.ctrlKey || e.metaKey) && e.key === 's' && !isInputFocused()) {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent('stop-all-jobs'));
      }

      // Alt+1-4: Navigate to pipeline steps
      if (e.altKey && ['1', '2', '3', '4'].includes(e.key)) {
        e.preventDefault();
        const tabMap: Record<string, string> = {
          '1': 'dataset_params',
          '2': 'training',
          '3': 'eval',
          '4': 'feedback',
        };
        window.dispatchEvent(
          new CustomEvent('navigate-tab', { detail: { tab: tabMap[e.key] } }),
        );
      }

      // Ctrl+R / Cmd+R: Refresh data (when no input is focused)
      if ((e.ctrlKey || e.metaKey) && e.key === 'r' && !isInputFocused()) {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent('refresh-data'));
      }
    };

    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);
}
