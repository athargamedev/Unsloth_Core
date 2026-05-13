import { useState } from 'react';
import { fetchOptionalJson, type Telemetry } from '../api';

export function useTelemetry() {
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null);

  const fetchTelemetry = async () => {
    const data = await fetchOptionalJson<Telemetry>('/api/telemetry');
    setTelemetry(data);
  };

  return { telemetry, setTelemetry, fetchTelemetry };
}
