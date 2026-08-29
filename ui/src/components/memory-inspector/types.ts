import type { StoredMemoryFile } from '../../lib/api';

export type InspectorTab = 'overview' | 'chat' | 'sources' | 'episodes' | 'claims' | 'reconsolidation' | 'dream-runs' | 'files';
export type StoredFileGroup = 'index' | 'archive';
export type SelectedFile = StoredMemoryFile & { group: StoredFileGroup };
