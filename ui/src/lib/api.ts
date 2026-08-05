import axios from 'axios';

export const apiOrigin = import.meta.env.VITE_API_ORIGIN ?? `${window.location.protocol}//${window.location.hostname}:8000`;

const api = axios.create({
  baseURL: `${apiOrigin}/api`,
});

export default api;

export function engramAudioUrl(meetingId: string) {
  return `${apiOrigin}/api/engram/meetings/${encodeURIComponent(meetingId)}/audio`;
}

export interface Message {
  role: string;
  content: string;
  loaded_pages?: LoadedPage[];
  tool_events?: ToolEvent[];
}

export interface ToolEvent {
  tool_name: string;
  arguments: Record<string, unknown>;
  result: string;
  failed?: boolean;
  truncated?: boolean;
}

export interface LoadedPage {
  slug: string;
  title: string;
  confidence: number;
  importance?: number;
  version: number;
}

export interface Session {
  id: string;
  query: string;
  transcript?: Message[];
}

export interface WikiPage {
  slug: string;
  title: string;
  content?: string;
  version?: number;
  confidence: number;
  importance?: number;
  tags: string[];
  related?: { target: string; relation: string }[];
  update_log?: { version: number; reason: string; date: string }[];
  source_log_entries?: string[];
}

export interface LogFile {
  filename: string;
  content?: string;
}

export interface ChatEpisodeState {
  session_id: string;
  query: string;
  transcript_turns: number;
  episode_seq?: number | null;
  active_episode?: Record<string, unknown> | null;
  encoded_episodes: Record<string, unknown>[];
}

export interface ArtifactSourceSegment {
  segment_id: string;
  index: number;
  content: string;
  speaker?: string | null;
  role?: string | null;
  timestamp?: string | null;
  start_seconds?: number | null;
  end_seconds?: number | null;
  metadata: Record<string, unknown>;
}

export interface ArtifactSourceSummary {
  source_id: string;
  source_type: string;
  session_id: string;
  recorded_at: string;
  occurred_at?: string | null;
  participants: string[];
  raw_log_entry_id?: string | null;
  metadata: Record<string, unknown>;
  segment_count: number;
}

export interface ArtifactSource extends Omit<ArtifactSourceSummary, 'segment_count'> {
  segments: ArtifactSourceSegment[];
}

export interface EpisodeArtifact {
  episode_id: string;
  source_id: string;
  source_type: string;
  occurred_at?: string | null;
  participants: string[];
  segment_ids: string[];
  claim_ids: string[];
  ignored_segment_ids: string[];
  extraction_status: string;
  extraction_error?: string | null;
}

export interface ClaimProvenanceArtifact {
  source_id: string;
  segment_ids: string[];
  raw_log_entry_id?: string | null;
  speaker?: string | null;
  evidence_type: string;
}

export interface MemoryClaimArtifact {
  claim_id: string;
  text: string;
  kind: string;
  about: Record<string, string>[];
  provenance: ClaimProvenanceArtifact[];
  recorded_at: string;
  status: string;
  confidence: number;
  inferred: boolean;
  slot?: string | null;
  facets: Record<string, unknown>;
  links: Record<string, string>[];
  page_slugs: string[];
  salience: number;
  claim_type: string;
  predicate?: string | null;
  evidence_modality: string;
  temporal_status: string;
  derivation_operation?: string | null;
  dream_disposition: string;
  dream_disposition_reason?: string | null;
  dream_run_id?: string | null;
  dream_disposition_at?: string | null;
}

export interface DreamClaimDecisionArtifact {
  claim_id: string;
  evidence_id: string;
  source_id: string;
  raw_log_entry_id?: string | null;
  disposition: string;
  reason: string;
  page_slugs: string[];
}

export interface DreamRunArtifact {
  run_id: string;
  started_at: string;
  completed_at: string;
  status: string;
  source_ids: string[];
  completed_source_ids: string[];
  pending_source_ids: string[];
  pages_created: number;
  pages_updated: number;
  claim_decisions: DreamClaimDecisionArtifact[];
  failures: Record<string, string>[];
}

export interface ArtifactCoverage {
  sources: number;
  episodes: number;
  claims: number;
  active_claims: number;
  suppressed_claims: number;
  segments: number;
  claimed_segments: number;
  segment_coverage: number;
  ignored_segments: number;
  accounted_segments: number;
  accounted_coverage: number;
  unassigned_segment_ids: string[];
  unaccounted_segment_ids: string[];
  unassigned_claim_ids: string[];
  unresolved_provenance_ids: string[];
  failed_episode_ids: string[];
  partial_episode_ids: string[];
}

export interface ArtifactOverview {
  coverage: ArtifactCoverage;
  projection: {
    page_assignments: number;
    assigned_claims: number;
    multi_page_claims: number;
    average_pages_per_claim: number;
    max_pages_per_claim: number;
  };
  integrity: {
    healthy: boolean;
    issues: Record<string, string[]>;
  };
  dream_audit: {
    runs: number;
    claim_dispositions: Record<string, number>;
  };
  labile_pages: number;
  archived_pages: number;
}

export interface StoredMemoryFile {
  filename: string;
  content: string;
}

export interface StoredMemoryFiles {
  wiki_index?: StoredMemoryFile | null;
  labile_pages: StoredMemoryFile[];
  archived_pages: StoredMemoryFile[];
}

export interface EngramActionItem {
  owner?: string | null;
  task: string;
  due?: string | null;
}

export interface EngramSummary {
  summary: string;
  decisions: string[];
  action_items: EngramActionItem[];
  open_questions: string[];
}

export interface EngramSegment {
  id: number | null;
  meeting_id: string;
  segment_index: number;
  start_seconds: number;
  end_seconds: number;
  text: string;
  speaker?: string | null;
  display_speaker?: string | null;
  status: 'live' | 'final' | 'diarized';
  created_at: string | null;
}

export interface EngramMeeting {
  id: string;
  title: string;
  status: 'ready' | 'transcribing' | 'processing' | 'reviewing' | 'completed' | 'failed';
  created_at: string | null;
  started_at: string | null;
  ended_at: string | null;
  duration_seconds?: number | null;
  audio_path?: string | null;
  error?: string | null;
  memory_log_entry_id?: string | null;
  summary?: EngramSummary | null;
  speaker_names: Record<string, string>;
  segment_count: number;
  segments?: EngramSegment[];
}
