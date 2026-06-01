import os from "os";
import fs from "fs";
import { execSync } from "child_process";
import type { TelemetryPayload, GpuTelemetry } from "../types";

// ── Network Sampling ───────────────────────────────────────────────────────

interface NetworkSample {
  rx: number;
  tx: number;
  timestamp: number;
}

let previousNetworkSample: NetworkSample = {
  rx: 0,
  tx: 0,
  timestamp: 0,
};

// ── Implementation ─────────────────────────────────────────────────────────

function readNetworkTotals(): { rx: number; tx: number } {
  try {
    const procNet = fs.readFileSync("/proc/net/dev", "utf8");
    return procNet
      .split("\n")
      .slice(2)
      .map((line) => line.trim())
      .filter(Boolean)
      .reduce(
        (acc, line) => {
          const parts = line.split(/\s+/);
          if (parts.length < 17) return acc;
          const iface = parts[0].replace(":", "");
          if (iface === "lo") return acc;
          acc.rx += Number(parts[1]) || 0;
          acc.tx += Number(parts[9]) || 0;
          return acc;
        },
        { rx: 0, tx: 0 },
      );
  } catch {
    return { rx: 0, tx: 0 };
  }
}

export function parseNvidiaSmiTelemetry(): GpuTelemetry | null {
  try {
    const output = execSync(
      "nvidia-smi --query-gpu=name,utilization.gpu,memory.total,memory.used,temperature.gpu --format=csv,noheader,nounits",
      { encoding: "utf8", timeout: 5000 },
    ).trim();

    if (!output) return null;
    const firstLine = output.split("\n")[0].trim();
    const [name, util, memoryTotal, memoryUsed, temperature] = firstLine.split(",").map((value) => value.trim());

    return {
      gpuName: name || "GPU",
      gpuLoad: Number(util) || 0,
      gpuMemoryTotalGB: Math.round((Number(memoryTotal) / 1024) * 10) / 10,
      gpuMemoryUsedGB: Math.round((Number(memoryUsed) / 1024) * 10) / 10,
      gpuTemperature: Number(temperature) || 0,
    };
  } catch {
    return null;
  }
}

/**
 * Builds a complete telemetry payload with GPU, CPU, memory, and network stats.
 */
export function buildTelemetryPayload(nodeId: string): TelemetryPayload {
  const gpuTelemetry = parseNvidiaSmiTelemetry();
  const totalMemory = os.totalmem();
  const freeMemory = os.freemem();
  const usedMemoryBytes = totalMemory - freeMemory;
  const cpuCount = Math.max(os.cpus().length, 1);
  const cpuLoad = Math.round((os.loadavg()[0] / cpuCount) * 100);
  const networkTotals = readNetworkTotals();
  const now = Date.now();
  let rxMBps = 0;
  let txMBps = 0;

  if (previousNetworkSample.timestamp > 0) {
    const elapsedSeconds = Math.max((now - previousNetworkSample.timestamp) / 1000, 0.5);
    rxMBps = Math.max(0, (networkTotals.rx - previousNetworkSample.rx) / elapsedSeconds / 1024 / 1024);
    txMBps = Math.max(0, (networkTotals.tx - previousNetworkSample.tx) / elapsedSeconds / 1024 / 1024);
  }

  previousNetworkSample = {
    rx: networkTotals.rx,
    tx: networkTotals.tx,
    timestamp: now,
  };

  return {
    gpuLoad: gpuTelemetry?.gpuLoad ?? 0,
    gpuTemperature: gpuTelemetry?.gpuTemperature ?? 0,
    gpuMemoryUsedGB: gpuTelemetry?.gpuMemoryUsedGB ?? 0,
    gpuMemoryTotalGB: gpuTelemetry?.gpuMemoryTotalGB ?? 0,
    gpuName: gpuTelemetry?.gpuName ?? "GPU",
    cpuLoad: Math.max(0, Math.min(cpuLoad, 999)),
    memoryUsedGB: Math.round((usedMemoryBytes / 1024 / 1024 / 1024) * 10) / 10,
    memoryTotalGB: Math.round((totalMemory / 1024 / 1024 / 1024) * 10) / 10,
    platform: os.platform(),
    nodeVersion: process.version,
    nodeId,
    timestamp: new Date().toISOString(),
    networkRxMBps: Math.round(rxMBps * 10) / 10,
    networkTxMBps: Math.round(txMBps * 10) / 10,
  };
}

/**
 * Reset the network sample state (e.g. for testing).
 */
export function resetNetworkSample(): void {
  previousNetworkSample = { rx: 0, tx: 0, timestamp: 0 };
}
