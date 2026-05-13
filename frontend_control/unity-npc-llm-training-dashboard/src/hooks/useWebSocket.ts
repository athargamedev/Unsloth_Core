import { useEffect, useRef, useState, useCallback } from 'react';
import type { Telemetry } from '../api';

interface UseWebSocketOptions {
  onTelemetry?: (data: Telemetry) => void;
  onJobUpdate?: (data: { id: string; status: string; loss: number | null; progress: number; wandbUrl?: string }) => void;
  onFallbackPolling?: () => void;
  onResync?: () => void;
}

type ConnectionQuality = 'connected' | 'reconnecting' | 'disconnected' | 'fallback-polling';

export function useWebSocket(options: UseWebSocketOptions) {
  const { onTelemetry, onJobUpdate, onFallbackPolling, onResync } = options;
  const [isConnected, setIsConnected] = useState(false);
  const [connectionQuality, setConnectionQuality] = useState<ConnectionQuality>('disconnected');
  const wsRef = useRef<WebSocket | null>(null);
  const retryCountRef = useRef(0);
  const maxRetries = 10;
  const fallbackTriggeredRef = useRef(false);
  const lastEventIdRef = useRef(0);

  const connect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host || 'localhost:3100';
    const url = `${protocol}//${host}/ws`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      setConnectionQuality('connected');
      retryCountRef.current = 0;
      fallbackTriggeredRef.current = false;

      ws.send(JSON.stringify({
        type: 'request_replay',
        sinceEventId: lastEventIdRef.current,
      }));

      onResync?.();
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);

        if (typeof msg.eventId === 'number' && Number.isFinite(msg.eventId)) {
          lastEventIdRef.current = Math.max(lastEventIdRef.current, msg.eventId);
        }

        if (msg.type === 'status' && typeof msg.payload?.lastEventId === 'number') {
          lastEventIdRef.current = Math.max(lastEventIdRef.current, msg.payload.lastEventId);
          return;
        }

        if (msg.type === 'ping') {
          ws.send(JSON.stringify({ type: 'pong', at: Date.now() }));
          return;
        }

        if (msg.type === 'replay' && Array.isArray(msg.payload?.events)) {
          for (const evt of msg.payload.events) {
            if (typeof evt.eventId === 'number' && Number.isFinite(evt.eventId)) {
              lastEventIdRef.current = Math.max(lastEventIdRef.current, evt.eventId);
            }
            if (evt.type === 'telemetry' && onTelemetry) {
              onTelemetry(evt.payload);
            } else if (evt.type === 'job_update' && onJobUpdate) {
              onJobUpdate(evt.payload);
            }
          }
          return;
        }

        if (msg.type === 'telemetry' && onTelemetry) {
          onTelemetry(msg.payload);
        } else if (msg.type === 'job_update' && onJobUpdate) {
          onJobUpdate(msg.payload);
        }
      } catch {
        // ignore malformed messages
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      if (retryCountRef.current < maxRetries) {
        setConnectionQuality('reconnecting');
        const delay = Math.min(1000 * Math.pow(2, retryCountRef.current), 30000);
        retryCountRef.current += 1;
        setTimeout(connect, delay);
      } else {
        setConnectionQuality('fallback-polling');
        if (!fallbackTriggeredRef.current) {
          fallbackTriggeredRef.current = true;
          onFallbackPolling?.();
        }
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [onTelemetry, onJobUpdate, onFallbackPolling, onResync]);

  useEffect(() => {
    connect();
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return { isConnected, connectionQuality };
}
