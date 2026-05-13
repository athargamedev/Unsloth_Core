import { useState } from 'react';
import { fetchJson, fetchOptionalJson, type SystemStatus, type HealthCheck } from '../api';

export function useSystemStatus() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [health, setHealth] = useState<HealthCheck | null>(null);

  const fetchStatus = async () => {
    const [statusData, healthData] = await Promise.all([
      fetchJson<SystemStatus>('/api/system/status'),
      fetchOptionalJson<HealthCheck>('/api/health'),
    ]);
    setStatus(statusData);
    setHealth(healthData);
  };

  const toggleExecutionMode = async () => {
    if (!status) return;
    const nextMode = status.executionMode === 'local' ? 'remote' : 'local';
    const response = await fetch('/api/execution-mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: nextMode }),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.error || 'Failed to toggle execution mode');
    }
    const result = await response.json();
    setStatus((prev) => (prev ? { ...prev, executionMode: result.mode } : prev));
  };

  return { status, setStatus, health, setHealth, fetchStatus, toggleExecutionMode };
}
