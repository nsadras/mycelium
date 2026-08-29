import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

import type { EngramMeeting, EngramSegment } from '../../lib/api';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatTime(seconds: number) {
  const safe = Math.max(0, Math.floor(seconds));
  const mins = Math.floor(safe / 60);
  const secs = safe % 60;
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

export function statusTone(status: EngramMeeting['status']) {
  if (status === 'completed') return 'bg-emerald-500/15 text-emerald-200 border-emerald-500/25';
  if (status === 'failed') return 'bg-rose-500/15 text-rose-200 border-rose-500/25';
  if (status === 'reviewing') return 'bg-violet-500/15 text-violet-100 border-violet-500/25';
  if (status === 'ready') return 'bg-sky-500/15 text-sky-100 border-sky-500/25';
  return 'bg-amber-500/15 text-amber-100 border-amber-500/25';
}

export function isBusyStatus(status: EngramMeeting['status']) {
  return status === 'transcribing' || status === 'processing';
}

export function processingLabel(meeting: EngramMeeting, isFinalizing: boolean) {
  if (isFinalizing) return 'Finalizing meeting';
  if (meeting.status === 'transcribing') return 'Transcribing audio';
  if (meeting.status === 'processing') return meeting.segments?.length ? 'Diarizing speakers' : 'Processing audio';
  return 'Processing';
}

export interface TranscriptTurn {
  key: string;
  speaker: string | null;
  speakerName: string | null;
  startSeconds: number;
  endSeconds: number;
  text: string;
  segments: EngramSegment[];
}

const SPEAKER_STYLES = [
  { avatar: 'border-cyan-400/30 bg-cyan-500/15 text-cyan-100', swatch: 'bg-cyan-400' },
  { avatar: 'border-amber-400/30 bg-amber-500/15 text-amber-100', swatch: 'bg-amber-400' },
  { avatar: 'border-violet-400/30 bg-violet-500/15 text-violet-100', swatch: 'bg-violet-400' },
  { avatar: 'border-rose-400/30 bg-rose-500/15 text-rose-100', swatch: 'bg-rose-400' },
  { avatar: 'border-sky-400/30 bg-sky-500/15 text-sky-100', swatch: 'bg-sky-400' },
] as const;

export function speakerStyle(speaker: string) {
  let hash = 0;
  for (const char of speaker) hash = ((hash * 31) + char.charCodeAt(0)) >>> 0;
  return SPEAKER_STYLES[hash % SPEAKER_STYLES.length];
}

export function speakerInitials(name: string) {
  const rawSpeaker = name.trim().match(/^SPEAKER[_\s-]*(\d+)$/i);
  if (rawSpeaker) return rawSpeaker[1];
  const words = name.trim().split(/[\s_]+/).filter(Boolean);
  if (words.length > 1) return `${words[0][0]}${words.at(-1)?.[0] ?? ''}`.toUpperCase();
  return name.replace(/[^a-zA-Z0-9]/g, '').slice(0, 2).toUpperCase() || '?';
}

export function nextSpeakerLabel(labels: string[]) {
  const used = new Set(labels);
  const highest = labels.reduce((current, label) => {
    const match = label.match(/^SPEAKER_(\d+)$/i);
    return match ? Math.max(current, Number(match[1])) : current;
  }, -1);
  let next = highest + 1;
  let label = `SPEAKER_${String(next).padStart(2, '0')}`;
  while (used.has(label)) {
    next += 1;
    label = `SPEAKER_${String(next).padStart(2, '0')}`;
  }
  return label;
}

export function transcriptTurns(segments: EngramSegment[], speakerNames: Record<string, string>): TranscriptTurn[] {
  const hasDiarizedSpeakers = segments.some(
    segment => segment.status === 'diarized' && segment.speaker && segment.speaker !== 'Speaker ?'
  );
  if (!hasDiarizedSpeakers) {
    return segments.map(segment => ({
      key: String(segment.id ?? `${segment.segment_index}-${segment.start_seconds}`),
      speaker: null,
      speakerName: null,
      startSeconds: segment.start_seconds,
      endSeconds: segment.end_seconds,
      text: segment.text,
      segments: [segment],
    }));
  }
  const turns: TranscriptTurn[] = [];
  for (const segment of segments) {
    const speaker = segment.status === 'diarized' && segment.speaker && segment.speaker !== 'Speaker ?'
      ? segment.speaker
      : null;
    const previous = turns.at(-1);
    if (speaker && previous?.speaker === speaker) {
      previous.endSeconds = segment.end_seconds;
      previous.text = `${previous.text} ${segment.text}`.trim();
      previous.segments.push(segment);
      continue;
    }
    turns.push({
      key: String(segment.id ?? `${segment.segment_index}-${segment.start_seconds}`),
      speaker,
      speakerName: speaker ? speakerNames[speaker]?.trim() || segment.display_speaker || speaker : null,
      startSeconds: segment.start_seconds,
      endSeconds: segment.end_seconds,
      text: segment.text,
      segments: [segment],
    });
  }
  return turns;
}
