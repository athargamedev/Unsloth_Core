import { useState } from 'react';
import {
  fetchJson,
  fetchOptionalJson,
  type Dataset,
  type Subject,
  type RunArtifact,
  type ExportArtifact,
  type AvailableCommand,
} from '../api';

export function useDatasets() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [runs, setRuns] = useState<RunArtifact[]>([]);
  const [exportArtifacts, setExportArtifacts] = useState<ExportArtifact[]>([]);
  const [availableCommands, setAvailableCommands] = useState<AvailableCommand[]>([]);
  const [commandSchemas, setCommandSchemas] = useState<Record<string, any>>({});

  const fetchDatasets = async () => {
    const [datasetsData, commandsData, subjectsData, commandSchemasData] = await Promise.all([
      fetchJson<Dataset[]>('/api/datasets'),
      fetchJson<AvailableCommand[]>('/api/available-commands'),
      fetchJson<Subject[]>('/api/subjects'),
      fetchOptionalJson<Record<string, any>>('/api/command-schemas'),
    ]);
    const [runsData, exportsData] = await Promise.all([
      fetchOptionalJson<RunArtifact[]>('/api/runs'),
      fetchOptionalJson<ExportArtifact[]>('/api/exports'),
    ]);
    setDatasets(datasetsData);
    setAvailableCommands(commandsData);
    setSubjects(subjectsData);
    setCommandSchemas(commandSchemasData ?? {});
    setRuns(runsData ?? []);
    setExportArtifacts(exportsData ?? []);
  };

  return {
    datasets,
    setDatasets,
    subjects,
    setSubjects,
    runs,
    setRuns,
    exportArtifacts,
    setExportArtifacts,
    availableCommands,
    setAvailableCommands,
    commandSchemas,
    setCommandSchemas,
    fetchDatasets,
  };
}
