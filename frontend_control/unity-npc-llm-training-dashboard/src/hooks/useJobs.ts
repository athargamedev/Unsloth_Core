import { useState, useMemo } from 'react';
import { fetchJson, type Job } from '../api';

export function useJobs() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [selectedJobIds, setSelectedJobIds] = useState<string[]>([]);
  const [activeFilter, setActiveFilter] = useState<'all' | 'running'>('all');

  const fetchJobs = async () => {
    const data = await fetchJson<Job[]>('/api/jobs');
    setJobs(data);
  };

  const stopJob = async (id: string) => {
    const response = await fetch('/api/commands/stop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id }),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.error || 'Failed to stop job');
    }
  };

  const filteredJobs = useMemo(
    () => (activeFilter === 'running' ? jobs.filter((job) => job.status === 'running') : jobs),
    [jobs, activeFilter],
  );

  const toggleJobSelection = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    setSelectedJobIds((prev) =>
      prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id],
    );
  };

  const downloadCsv = (rows: Array<Array<string | number>>, fileName: string) => {
    const csv = rows
      .map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(','))
      .join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.href = url;
    link.setAttribute('download', fileName);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const exportJobsCsv = () => {
    const rows = [
      ['id', 'name', 'type', 'status', 'progress', 'loss', 'createdAt', 'startedAt', 'finishedAt'],
      ...jobs.map((job) => [
        job.id,
        job.name,
        job.type,
        job.status,
        job.progress,
        job.loss ?? '',
        job.createdAt,
        job.startedAt ?? '',
        job.finishedAt ?? '',
      ]),
    ];
    downloadCsv(rows, 'ucore_jobs.csv');
  };

  return {
    jobs,
    setJobs,
    selectedJobId,
    setSelectedJobId,
    selectedJobIds,
    setSelectedJobIds,
    activeFilter,
    setActiveFilter,
    filteredJobs,
    stopJob,
    toggleJobSelection,
    exportJobsCsv,
    fetchJobs,
  };
}
