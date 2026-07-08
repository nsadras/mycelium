import axios from 'axios';

export const apiOrigin = import.meta.env.VITE_API_ORIGIN ?? `${window.location.protocol}//${window.location.hostname}:8000`;

const api = axios.create({
  baseURL: `${apiOrigin}/api`,
});

export default api;

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
  retrievability?: number;
  stability_days?: number;
  difficulty?: number;
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
  stability_days?: number;
  difficulty?: number;
  retrievability?: number;
  last_accessed?: string | null;
  last_reviewed?: string | null;
  review_count?: number;
  reinforced_count?: number;
  conflict_count?: number;
  pinned?: boolean;
  tags: string[];
  related?: { target: string; relation: string }[];
  update_log?: { version: number; reason: string; date: string }[];
  source_log_entries?: string[];
}

export interface LogFile {
  filename: string;
  content?: string;
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
  status: 'live' | 'final' | 'diarized';
  created_at: string | null;
}

export interface EngramMeeting {
  id: string;
  title: string;
  status: 'ready' | 'transcribing' | 'processing' | 'completed' | 'failed';
  created_at: string | null;
  started_at: string | null;
  ended_at: string | null;
  duration_seconds?: number | null;
  audio_path?: string | null;
  error?: string | null;
  memory_log_entry_id?: string | null;
  summary?: EngramSummary | null;
  segment_count: number;
  segments?: EngramSegment[];
}

export function engramStreamUrl(meetingId: string) {
  const wsOrigin = apiOrigin.replace(/^http/, 'ws');
  return `${wsOrigin}/api/engram/meetings/${meetingId}/stream`;
}
