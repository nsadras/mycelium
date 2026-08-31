import type { StoredMemoryFileSummary } from '../../lib/api';

export type InspectorTab = 'overview' | 'chat' | 'sources' | 'episodes' | 'claims' | 'facts' | 'entities' | 'identity' | 'organization' | 'reconsolidation' | 'dream-runs' | 'files';
export type StoredFileGroup = 'index' | 'archive';
export type SelectedFile = StoredMemoryFileSummary & { group: StoredFileGroup; content?: string };
