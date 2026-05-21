import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from './useReactQuery';
import type { Telemetry, WsMessage } from '../api';

/**
 * Syncs WebSocket events with React Query cache.
 *
 * - `telemetry` → `queryClient.setQueryData` (avoids a network round-trip)
 * - `job_update` → `queryClient.invalidateQueries` (triggers a fresh fetch)
 * - `logs_cleared` → invalidates logs so the next read is empty
 *
 * Attach this once at the app root after establishing a WebSocket connection.
 */
export function useWebSocketQuery(ws: WebSocket | null) {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!ws) return;

    const handler = (event: MessageEvent) => {
      let msg: WsMessage;
      try {
        msg = JSON.parse(event.data) as WsMessage;
      } catch {
        return; // ignore malformed messages
      }

      // WsMessage.type is 'telemetry' | 'job_update' | 'status',
      // but the server may send other types (logs_cleared, ping, replay).
      const msgType: string = msg.type;

      if (msgType === 'telemetry') {
        // Optimistically update the telemetry cache without a fetch.
        const payload = msg.payload as Telemetry;
        if (payload && typeof payload.gpuLoad === 'number') {
          queryClient.setQueryData(queryKeys.telemetry, payload);
        }
      } else if (msgType === 'job_update') {
        // A job's status / progress changed — refetch the full job list.
        queryClient.invalidateQueries({ queryKey: queryKeys.jobs.all });
      } else if (msgType === 'logs_cleared') {
        queryClient.invalidateQueries({ queryKey: queryKeys.logs });
      }
      // All other message types (status, ping/pong, replay) are
      // protocol-level and need no cache action.
    };

    ws.addEventListener('message', handler);
    return () => ws.removeEventListener('message', handler);
  }, [ws, queryClient]);
}
