import axios from 'axios';

const apiOrigin = import.meta.env.VITE_API_ORIGIN ?? `${window.location.protocol}//${window.location.hostname}:8000`;

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

export interface LlmSettings {
  provider: string;
  model: string;
  url: string;
  temperature: number;
  timeout_seconds: number;
  max_retries: number;
}

export interface LlmPreset {
  id: string;
  label: string;
  provider: string;
  url: string;
  model: string;
}

export interface LlmModelOption {
  id: string;
  label: string;
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
