import { useEffect, useRef, useState, useCallback } from 'react';
import type { Telemetry } from '../api';

interface UseWebSocketOptions {
  onTelemetry?: (data: Telemetry) => void;
  onJobUpdate?: (data: { id: string; status: string; loss: number | null; progress: number }) => void;
  onFallbackPolling?: () => void;
}

type ConnectionQuality = 'connected' | 'reconnecting' | 'disconnected' | 'fallback-polling';

export function useWebSocket(options: UseWebSocketOptions) {
  const { onTelemetry, onJobUpdate, onFallbackPolling } = options;
  const [isConnected, setIsConnected] = useState(false);
  const [connectionQuality, setConnectionQuality] = useState<ConnectionQuality>('disconnected');
  const wsRef = useRef<WebSocket | null>(null);
  const retryCountRef = useRef(0);
  const maxRetries = 10;
  const fallbackTriggeredRef = useRef(false);

  const connect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.hostname || 'localhost';
    const url = `${protocol}//${host}:3100/ws`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      setConnectionQuality('connected');
      retryCountRef.current = 0;
      fallbackTriggeredRef.current = false;
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
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
  }, [onTelemetry, onJobUpdate, onFallbackPolling]);

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
