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
  timestamp: string;
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

export type PageType = 'you' | 'person' | 'project' | 'series' | 'event' | 'artifact' | 'topic' | 'organization' | 'place';

export interface WikiPage {
  slug: string;
  title: string;
  content?: string;
  version?: number;
  confidence: number;
  importance?: number;
  page_type: PageType | null;
  tags: string[];
  related?: { target: string; relation: string }[];
  update_log?: { version: number; reason: string; date: string }[];
  source_log_entries?: string[];
  entity_id: string;
  entity_status: 'active' | 'archived' | 'merged';
  aliases: string[];
  sections?: WikiSection[];
  redirected_from?: string;
}

export interface WikiSourceReference {
  source_id: string;
  segment_ids: string[];
  raw_log_entry_id?: string | null;
  speaker?: string | null;
}

export interface WikiFactItem {
  kind: 'fact';
  fact_id: string;
  text: string;
  claim_ids: string[];
  canonical_owner_entity_ids: string[];
  canonical_linked_entity_ids: string[];
  projection: 'canonical' | 'shared_endpoint';
  relationship_kind: 'project_role' | null;
  synthesis_origin: 'claim' | 'model' | 'manual';
  synthesis_confidence: number;
  synthesis_reason: string;
  manual_text: boolean;
  qualifiers: string[];
  evidence_modality: string;
  sources: WikiSourceReference[];
  links: { entity_id: string; slug: string; title: string }[];
  authoritative: boolean;
}

export interface WikiLinkItem {
  kind: 'link';
  entity_id: string;
  slug: string;
  title: string;
  entity_type: PageType;
}

export interface WikiEncounterItem {
  kind: 'encounter';
  encounter_id: string;
  text: string;
  source_id: string;
  raw_log_entry_id?: string | null;
}

export interface WikiSection {
  key: string;
  title: string;
  items: (WikiFactItem | WikiLinkItem | WikiEncounterItem)[];
}

export interface EntityRecord {
  entity_id: string;
  entity_type: PageType;
  title: string;
  slug: string;
  aliases: string[];
  status: 'active' | 'archived' | 'merged';
  created_at: string;
  updated_at: string;
  merged_into_entity_id?: string | null;
}

export interface ClaimPlacementArtifact {
  claim_id: string;
  owner_entity_id?: string | null;
  section_key?: string | null;
  linked_entity_ids: string[];
  status: 'placed' | 'deferred';
  reason: string;
  created_at: string;
  updated_at: string;
}

export interface OrganizationProposalArtifact {
  proposal_id: string;
  proposal_type: 'assign_claim' | 'merge_entities';
  explanation: string;
  confidence: number;
  created_at: string;
  claim_id?: string | null;
  proposed_owner_entity_id?: string | null;
  proposed_section_key?: string | null;
  proposed_new_entity_type?: PageType | null;
  proposed_new_entity_title?: string | null;
  source_entity_id?: string | null;
  target_entity_id?: string | null;
  status: 'pending' | 'rejected' | 'applied' | 'stale';
  reviewer_note?: string | null;
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
  about: Record<string, string>[];
  provenance: ClaimProvenanceArtifact[];
  recorded_at: string;
  status: string;
  confidence: number;
  slot?: string | null;
  facets: Record<string, unknown>;
  links: Record<string, string>[];
  placement?: ClaimPlacementArtifact | null;
  claim_type: string;
  predicate?: string | null;
  evidence_modality: string;
  temporal_status: string;
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
  reconsolidation_proposal_ids: string[];
}

export interface ReconsolidationProposalArtifact {
  proposal_id: string;
  incoming_claim_id: string;
  target_claim_id: string;
  proposed_relation: 'contradicts' | 'supersedes';
  explanation: string;
  confidence: number;
  dream_run_id: string;
  created_at: string;
  affected_entity_ids: string[];
  status: 'pending' | 'approved' | 'rejected' | 'applied' | 'stale';
  reviewer_note?: string | null;
  reviewed_at?: string | null;
  applied_at?: string | null;
  application_error?: string | null;
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
  unplaced_claim_ids: string[];
  unresolved_provenance_ids: string[];
  failed_episode_ids: string[];
  partial_episode_ids: string[];
}

export interface ArtifactOverview {
  coverage: ArtifactCoverage;
  short_term_memory: {
    pending_claims: number;
    deferred_claims: number;
    retryable_failures: number;
    total_claims: number;
    oldest_pending_at?: string | null;
    oldest_deferred_at?: string | null;
    ready: boolean;
    reasons: string[];
    include_deferred: boolean;
  };
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
  reconsolidation_proposals: Record<string, number>;
  organization_proposals: Record<string, number>;
  archived_pages: number;
}

export interface StoredMemoryFile {
  filename: string;
  content: string;
}

export interface StoredMemoryFiles {
  wiki_index?: StoredMemoryFile | null;
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
