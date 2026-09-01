import type { StoredMemoryFileSummary } from '../../lib/api';

export type InspectorTab = 'overview' | 'review' | 'chat' | 'sources' | 'episodes' | 'claims' | 'facts' | 'entities' | 'identity' | 'organization' | 'reconsolidation' | 'dream-runs' | 'files';
export interface InspectorTarget {
  tab: InspectorTab;
  id?: string;
}
export type StoredFileGroup = 'index' | 'archive';
export type SelectedFile = StoredMemoryFileSummary & { group: StoredFileGroup; content?: string };
