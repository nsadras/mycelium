import { useEffect, useMemo, useRef, useState, type Dispatch, type MouseEvent, type SetStateAction } from 'react';
import { AlertTriangle, Check, CheckCircle2, CircleHelp, Clock, FileAudio, Gavel, ListChecks, Loader2, Pause, Pencil, Play, RotateCw, Save, Trash2, Upload, Volume2, VolumeX, X } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import api, { engramAudioUrl, type EngramMeeting, type EngramSegment } from '../lib/api';
import type { AssistantStatus } from '../lib/assistantStatus';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

function formatTime(seconds: number) {
  const safe = Math.max(0, Math.floor(seconds));
  const mins = Math.floor(safe / 60);
  const secs = safe % 60;
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

function statusTone(status: EngramMeeting['status']) {
  if (status === 'completed') return 'bg-emerald-500/15 text-emerald-200 border-emerald-500/25';
  if (status === 'failed') return 'bg-rose-500/15 text-rose-200 border-rose-500/25';
  if (status === 'reviewing') return 'bg-violet-500/15 text-violet-100 border-violet-500/25';
  if (status === 'ready') return 'bg-sky-500/15 text-sky-100 border-sky-500/25';
  return 'bg-amber-500/15 text-amber-100 border-amber-500/25';
}

function isBusyStatus(status: EngramMeeting['status']) {
  return status === 'transcribing' || status === 'processing';
}

function processingLabel(meeting: EngramMeeting, isFinalizing: boolean) {
  if (isFinalizing) return 'Finalizing meeting';
  if (meeting.status === 'transcribing') return 'Transcribing audio';
  if (meeting.status === 'processing') return meeting.segments?.length ? 'Diarizing speakers' : 'Processing audio';
  return 'Processing';
}

interface TranscriptTurn {
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

function speakerStyle(speaker: string) {
  let hash = 0;
  for (const char of speaker) hash = ((hash * 31) + char.charCodeAt(0)) >>> 0;
  return SPEAKER_STYLES[hash % SPEAKER_STYLES.length];
}

function speakerInitials(name: string) {
  const rawSpeaker = name.trim().match(/^SPEAKER[_\s-]*(\d+)$/i);
  if (rawSpeaker) return rawSpeaker[1];
  const words = name.trim().split(/[\s_]+/).filter(Boolean);
  if (words.length > 1) return `${words[0][0]}${words.at(-1)?.[0] ?? ''}`.toUpperCase();
  return name.replace(/[^a-zA-Z0-9]/g, '').slice(0, 2).toUpperCase() || '?';
}

function transcriptTurns(segments: EngramSegment[], speakerNames: Record<string, string>): TranscriptTurn[] {
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

interface EngramProps {
  setAssistantStatus: Dispatch<SetStateAction<AssistantStatus>>;
}

export default function Engram({ setAssistantStatus }: EngramProps) {
  const [meetings, setMeetings] = useState<EngramMeeting[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [meeting, setMeeting] = useState<EngramMeeting | null>(null);
  const [title, setTitle] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isSavingSpeakers, setIsSavingSpeakers] = useState(false);
  const [editingTranscriptTurn, setEditingTranscriptTurn] = useState<string | null>(null);
  const [savingTranscriptTurn, setSavingTranscriptTurn] = useState<string | null>(null);
  const [isFinalizing, setIsFinalizing] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [speakerNames, setSpeakerNames] = useState<Record<string, string>>({});
  const uploadRef = useRef<HTMLInputElement>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const pendingSeekRef = useRef<number | null>(null);
  const playbackAttemptedRef = useRef(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isBuffering, setIsBuffering] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [audioDuration, setAudioDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [isMuted, setIsMuted] = useState(false);
  const [playbackError, setPlaybackError] = useState<string | null>(null);

  const segments = useMemo(() => meeting?.segments ?? [], [meeting]);
  const turns = useMemo(() => transcriptTurns(segments, speakerNames), [segments, speakerNames]);
  const activeTurnKey = useMemo(
    () => turns.find(turn => currentTime >= turn.startSeconds && currentTime < turn.endSeconds)?.key ?? null,
    [currentTime, turns]
  );
  const speakerStats = useMemo(() => {
    const stats = new Map<string, { label: string; count: number; seconds: number }>();
    for (const segment of segments) {
      if (segment.status !== 'diarized' || !segment.speaker || segment.speaker === 'Speaker ?') continue;
      const label = segment.speaker;
      const current = stats.get(label) ?? { label, count: 0, seconds: 0 };
      current.count += 1;
      current.seconds += Math.max(0, segment.end_seconds - segment.start_seconds);
      stats.set(label, current);
    }
    return Array.from(stats.values()).sort((a, b) => a.label.localeCompare(b.label));
  }, [segments]);

  useEffect(() => {
    fetchMeetings();
    setAssistantStatus({ activity: 'engram', label: 'Engram', detail: 'Ready for meetings' });
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setMeeting(null);
      return;
    }
    fetchMeeting(selectedId);
  }, [selectedId]);

  useEffect(() => {
    setSpeakerNames(meeting?.speaker_names ?? {});
  }, [meeting?.id, JSON.stringify(meeting?.speaker_names ?? {})]);

  useEffect(() => {
    setEditingTranscriptTurn(null);
    setSavingTranscriptTurn(null);
    pendingSeekRef.current = null;
    playbackAttemptedRef.current = false;
    audioRef.current?.pause();
    setIsPlaying(false);
    setIsBuffering(false);
    setCurrentTime(0);
    setAudioDuration(0);
    setPlaybackError(null);
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId || meeting?.id !== selectedId || !isBusyStatus(meeting.status)) return;
    let cancelled = false;
    let pollTimer: ReturnType<typeof setTimeout> | null = null;

    const pollMeeting = async () => {
      try {
        const res = await api.get(`/engram/meetings/${selectedId}`);
        if (cancelled) return;
        const next = res.data as EngramMeeting;
        setMeeting(next);
        setMeetings(prev => prev.map(item => item.id === next.id ? { ...item, ...next } : item));
        if (next.status === 'failed') {
          setAssistantStatus({ activity: 'error', label: 'Engram failed', detail: 'Check meeting detail' });
        } else if (next.status === 'reviewing') {
          setAssistantStatus({ activity: 'engram', label: 'Review speakers', detail: next.title });
        } else if (next.status === 'completed') {
          setAssistantStatus({ activity: 'engram', label: 'Meeting complete', detail: 'Ready' });
        }
      } catch (err) {
        console.error('Failed to poll meeting', err);
      } finally {
        if (!cancelled) pollTimer = setTimeout(pollMeeting, 1500);
      }
    };

    pollTimer = setTimeout(pollMeeting, 1500);
    return () => {
      cancelled = true;
      if (pollTimer) clearTimeout(pollTimer);
    };
  }, [selectedId, meeting?.id, meeting?.status, setAssistantStatus]);

  useEffect(() => {
    if (transcriptRef.current) {
      transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
    }
  }, [segments.length]);

  const fetchMeetings = async () => {
    try {
      const res = await api.get('/engram/meetings');
      setMeetings(res.data);
      if (res.data.length > 0 && !selectedId) {
        setSelectedId(res.data[0].id);
      }
    } catch (err) {
      console.error('Failed to fetch meetings', err);
    }
  };

  const fetchMeeting = async (id: string) => {
    try {
      const res = await api.get(`/engram/meetings/${id}`);
      setMeeting(res.data);
      setMeetings(prev => prev.map(item => item.id === id ? { ...item, ...res.data } : item));
    } catch (err) {
      console.error('Failed to fetch meeting', err);
    }
  };

  const processMeeting = async () => {
    if (!meeting || isProcessing) return;
    setIsProcessing(true);
    setAssistantStatus({ activity: 'thinking', label: 'Processing meeting', detail: meeting.title });
    try {
      const res = await api.post(`/engram/meetings/${meeting.id}/process`);
      setMeeting(res.data);
      setMeetings(prev => prev.map(item => item.id === meeting.id ? { ...item, ...res.data } : item));
    } catch (err) {
      console.error('Failed to process meeting', err);
      setAssistantStatus({ activity: 'error', label: 'Processing failed', detail: 'Check backend logs' });
    } finally {
      setIsProcessing(false);
    }
  };

  const togglePlayback = async () => {
    const audio = audioRef.current;
    if (!audio || !meeting?.audio_path) return;
    if (!audio.paused) {
      audio.pause();
      return;
    }

    playbackAttemptedRef.current = true;
    setPlaybackError(null);
    setIsBuffering(true);
    try {
      if (audioDuration > 0 && audio.currentTime >= audioDuration - 0.05) audio.currentTime = 0;
      await audio.play();
    } catch (err) {
      console.error('Failed to play meeting audio', err);
      setIsPlaying(false);
      setIsBuffering(false);
      setPlaybackError('This recording could not be played in the browser.');
    }
  };

  const seekPlayback = (seconds: number) => {
    const audio = audioRef.current;
    if (!audio) return;
    const nextTime = Math.max(0, Math.min(seconds, audioDuration || seconds));
    setPlaybackError(null);
    if (audio.readyState < 1) {
      pendingSeekRef.current = nextTime;
      audio.load();
      return;
    }
    audio.currentTime = nextTime;
    setCurrentTime(nextTime);
  };

  const setPlaybackVolume = (nextVolume: number) => {
    const normalized = Math.max(0, Math.min(1, nextVolume));
    setVolume(normalized);
    if (audioRef.current) audioRef.current.volume = normalized;
    if (normalized > 0 && isMuted) {
      setIsMuted(false);
      if (audioRef.current) audioRef.current.muted = false;
    }
  };

  const toggleMute = () => {
    const nextMuted = !isMuted;
    setIsMuted(nextMuted);
    if (audioRef.current) audioRef.current.muted = nextMuted;
  };

  const saveSpeakerNames = async () => {
    if (!meeting || isSavingSpeakers) return null;
    setIsSavingSpeakers(true);
    try {
      const res = await api.put(`/engram/meetings/${meeting.id}/speakers`, { speaker_names: speakerNames });
      setMeeting(res.data);
      setMeetings(prev => prev.map(item => item.id === meeting.id ? { ...item, ...res.data } : item));
      return res.data as EngramMeeting;
    } catch (err) {
      console.error('Failed to save speaker names', err);
      setAssistantStatus({ activity: 'error', label: 'Speaker save failed', detail: 'Check backend logs' });
      return null;
    } finally {
      setIsSavingSpeakers(false);
    }
  };

  const saveTranscriptTurn = async (turn: TranscriptTurn, texts: string[]) => {
    if (!meeting || savingTranscriptTurn || texts.length !== turn.segments.length) return false;
    const updates = turn.segments.flatMap((segment, index) => (
      segment.id !== null && texts[index].trim() !== segment.text
        ? [{ id: segment.id, text: texts[index].trim() }]
        : []
    ));
    if (updates.length === 0) return true;

    setSavingTranscriptTurn(turn.key);
    try {
      const res = await api.put(`/engram/meetings/${meeting.id}/transcript`, { segments: updates });
      setMeeting(res.data);
      setMeetings(prev => prev.map(item => item.id === meeting.id ? { ...item, ...res.data } : item));
      return true;
    } catch (err) {
      console.error('Failed to save transcript', err);
      setAssistantStatus({ activity: 'error', label: 'Transcript save failed', detail: 'Review the edited text and try again' });
      return false;
    } finally {
      setSavingTranscriptTurn(null);
    }
  };

  const finalizeMeeting = async () => {
    if (!meeting || isFinalizing) return;
    setIsFinalizing(true);
    setAssistantStatus({ activity: 'thinking', label: 'Finalizing meeting', detail: meeting.title });
    try {
      const saved = await saveSpeakerNames();
      if (!saved) return;
      const res = await api.post(`/engram/meetings/${meeting.id}/finalize`);
      setMeeting(res.data);
      setMeetings(prev => prev.map(item => item.id === meeting.id ? { ...item, ...res.data } : item));
      setAssistantStatus({ activity: 'engram', label: 'Meeting complete', detail: res.data.title });
    } catch (err) {
      console.error('Failed to finalize meeting', err);
      setAssistantStatus({ activity: 'error', label: 'Finalize failed', detail: 'Check backend logs' });
    } finally {
      setIsFinalizing(false);
    }
  };

  const deleteMeeting = async (target: EngramMeeting) => {
    if (deletingId) return;
    const ok = window.confirm(`Delete "${target.title}" and its uploaded recording/transcript?`);
    if (!ok) return;
    setDeletingId(target.id);
    setAssistantStatus({ activity: 'engram', label: 'Deleting recording', detail: target.title });
    try {
      await api.delete(`/engram/meetings/${target.id}`);
      setMeetings(prev => {
        const next = prev.filter(item => item.id !== target.id);
        if (selectedId === target.id) {
          setSelectedId(next[0]?.id ?? null);
          setMeeting(null);
        }
        return next;
      });
      setAssistantStatus({ activity: 'engram', label: 'Recording deleted', detail: 'Ready' });
    } catch (err) {
      console.error('Failed to delete meeting', err);
      setAssistantStatus({ activity: 'error', label: 'Delete failed', detail: 'Check backend logs' });
    } finally {
      setDeletingId(null);
    }
  };

  const uploadRecording = async (file: File | null) => {
    if (!file || isUploading) return;
    setIsUploading(true);
    setAssistantStatus({ activity: 'engram', label: 'Uploading recording', detail: file.name });
    const form = new FormData();
    form.append('file', file);
    form.append('title', title.trim() || file.name.replace(/\.[^.]+$/, '') || 'Uploaded recording');
    try {
      const res = await api.post('/engram/meetings/upload', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setMeetings(prev => [res.data, ...prev]);
      setSelectedId(res.data.id);
      setTitle('');
      setAssistantStatus({ activity: 'engram', label: 'Raw recording ready', detail: res.data.title });
    } catch (err) {
      console.error('Failed to upload recording', err);
      setAssistantStatus({ activity: 'error', label: 'Upload failed', detail: 'Check backend logs' });
    } finally {
      setIsUploading(false);
      if (uploadRef.current) uploadRef.current.value = '';
    }
  };

  return (
    <div className="flex flex-col md:flex-row flex-1 min-h-0 min-w-0">
      {meeting?.audio_path && (
        <audio
          ref={audioRef}
          src={engramAudioUrl(meeting.id)}
          preload="metadata"
          className="hidden"
          onLoadedMetadata={(event) => {
            const audio = event.currentTarget;
            setAudioDuration(Number.isFinite(audio.duration) ? audio.duration : 0);
            audio.volume = volume;
            audio.muted = isMuted;
            if (pendingSeekRef.current !== null) {
              audio.currentTime = pendingSeekRef.current;
              setCurrentTime(pendingSeekRef.current);
              pendingSeekRef.current = null;
            }
          }}
          onDurationChange={(event) => {
            const nextDuration = event.currentTarget.duration;
            if (Number.isFinite(nextDuration)) setAudioDuration(nextDuration);
          }}
          onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
          onPlay={() => setIsPlaying(true)}
          onPause={() => {
            setIsPlaying(false);
            setIsBuffering(false);
          }}
          onPlaying={() => setIsBuffering(false)}
          onWaiting={(event) => {
            if (!event.currentTarget.paused) setIsBuffering(true);
          }}
          onCanPlay={() => setIsBuffering(false)}
          onEnded={() => {
            setIsPlaying(false);
            setIsBuffering(false);
          }}
          onError={() => {
            if (!playbackAttemptedRef.current) return;
            setIsPlaying(false);
            setIsBuffering(false);
            setPlaybackError('This recording could not be played in the browser.');
          }}
        />
      )}
      <div className="w-full md:w-72 h-64 md:h-full bg-white border-b md:border-b-0 md:border-r border-slate-200 flex flex-col shrink-0">
        <div className="p-4 border-b border-slate-200 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-slate-700 flex items-center gap-2">
              <FileAudio size={16} /> Engram
            </h2>
            <button onClick={fetchMeetings} title="Refresh meetings" className="p-1 hover:bg-slate-100 rounded-md text-indigo-600">
              <RotateCw size={16} />
            </button>
          </div>
          <div className="flex gap-2">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Recording title"
              className="min-w-0 flex-1 rounded-md px-2 py-1.5 text-sm"
            />
            <input
              ref={uploadRef}
              type="file"
              accept="audio/*,.wav,.mp3,.m4a,.flac,.ogg,.webm,.aac"
              className="hidden"
              onChange={(event) => uploadRecording(event.target.files?.[0] ?? null)}
            />
            <button
              onClick={() => uploadRef.current?.click()}
              disabled={isUploading}
              title="Upload raw recording"
              className="inline-flex items-center justify-center rounded-md border border-slate-200 px-2.5 text-indigo-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isUploading ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {meetings.map((item) => (
            <button
              key={item.id}
              onClick={() => setSelectedId(item.id)}
              className={cn(
                "w-full rounded-md px-3 py-2 text-left text-sm transition-colors",
                selectedId === item.id ? "bg-indigo-50 text-indigo-700 font-medium" : "hover:bg-slate-50 text-slate-600"
              )}
            >
              <div className="flex items-center gap-2">
                <span className="min-w-0 flex-1 truncate">{item.title}</span>
                <span
                  role="button"
                  tabIndex={0}
                  onClick={(event) => {
                    event.stopPropagation();
                    deleteMeeting(item);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      event.stopPropagation();
                      deleteMeeting(item);
                    }
                  }}
                  title="Delete recording"
                  className="inline-flex shrink-0 items-center justify-center rounded-md p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
                >
                  {deletingId === item.id ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
                </span>
              </div>
              <div className="mt-1 flex items-center gap-2 text-[10px] uppercase tracking-wide text-slate-500">
                <span>{item.status}</span>
                <span>{item.segment_count} lines</span>
              </div>
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 min-h-0 bg-white flex flex-col">
        {meeting ? (
          <>
            <div className="shrink-0 border-b border-slate-200 px-5 py-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <h1 className="truncate text-lg font-bold text-white">{meeting.title}</h1>
                  <span className={cn("rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide", statusTone(meeting.status))}>
                    {meeting.status}
                  </span>
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-slate-400">
                  <span className="inline-flex items-center gap-1"><Clock size={13} /> {meeting.duration_seconds ? `${Math.round(meeting.duration_seconds)}s` : 'Duration unknown'}</span>
                  {meeting.memory_log_entry_id && <span className="font-mono text-emerald-300">{meeting.memory_log_entry_id}</span>}
                  {meeting.audio_path && <span className="inline-flex min-w-0 items-center gap-1"><FileAudio size={13} /> <span className="truncate">{meeting.audio_path}</span></span>}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => deleteMeeting(meeting)}
                  disabled={deletingId === meeting.id || isBusyStatus(meeting.status)}
                  className="inline-flex items-center gap-2 rounded-md border border-rose-200 px-3 py-2 text-sm font-semibold text-rose-600 hover:bg-rose-50 disabled:opacity-50"
                >
                  {deletingId === meeting.id ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
                  Delete
                </button>
                {isBusyStatus(meeting.status) && (
                  <button
                    disabled
                    className="inline-flex items-center gap-2 rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white opacity-80"
                  >
                    <Loader2 size={16} className="animate-spin" />
                    {processingLabel(meeting, isFinalizing)}
                  </button>
                )}
                {(meeting.status === 'ready' || meeting.status === 'failed') && (
                  <button
                    onClick={processMeeting}
                    disabled={isProcessing}
                    className="inline-flex items-center gap-2 rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
                  >
                    {isProcessing ? <Loader2 size={16} className="animate-spin" /> : <RotateCw size={16} />}
                    {meeting.status === 'ready' ? 'Process' : 'Retry'}
                  </button>
                )}
                {meeting.status === 'reviewing' && (
                  <button
                    onClick={finalizeMeeting}
                    disabled={isFinalizing || isSavingSpeakers || Boolean(editingTranscriptTurn) || Boolean(savingTranscriptTurn)}
                    className="inline-flex items-center gap-2 rounded-md bg-emerald-600 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
                  >
                    {isFinalizing ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
                    Finalize
                  </button>
                )}
              </div>
            </div>

            {meeting.error && (
              <div className="mx-5 mt-4 rounded-md border border-rose-500/25 bg-rose-950/30 px-3 py-2 text-sm text-rose-100 flex items-start gap-2">
                <AlertTriangle size={16} className="mt-0.5 shrink-0" />
                <span>{meeting.error}</span>
              </div>
            )}

            <div className="grid flex-1 min-h-0 grid-cols-1 xl:grid-cols-[minmax(0,1fr)_360px]">
              <div className="flex min-h-0 flex-col">
                <div className="shrink-0 border-b border-slate-200 px-5 py-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">
                  Transcript
                </div>
                <div ref={transcriptRef} className="flex-1 min-h-0 overflow-y-auto px-5 py-2">
                  {segments.length === 0 ? (
                    <div className="h-full flex items-center justify-center text-slate-500">
                      {meeting.status === 'ready'
                        ? 'Raw audio is ready. Click Process to transcribe, diarize, summarize, and ingest it.'
                        : meeting.status === 'processing' || meeting.status === 'transcribing'
                          ? <ProcessingIndicator label={processingLabel(meeting, isFinalizing)} compact />
                          : 'No transcript segments.'}
                    </div>
                  ) : (
                    turns.map((turn) => (
                      <TranscriptTurnRow
                        key={turn.key}
                        turn={turn}
                        canPlay={Boolean(meeting.audio_path)}
                        isActive={activeTurnKey === turn.key}
                        canEdit={meeting.status === 'reviewing' && (!editingTranscriptTurn || editingTranscriptTurn === turn.key) && !savingTranscriptTurn}
                        isEditing={editingTranscriptTurn === turn.key}
                        isSaving={savingTranscriptTurn === turn.key}
                        onSeek={seekPlayback}
                        onEditingChange={editing => setEditingTranscriptTurn(editing ? turn.key : null)}
                        onSave={texts => saveTranscriptTurn(turn, texts)}
                      />
                    ))
                  )}
                </div>
                {meeting.audio_path && (
                  <AudioTransport
                    currentTime={currentTime}
                    duration={audioDuration}
                    volume={volume}
                    isMuted={isMuted}
                    isPlaying={isPlaying}
                    isBuffering={isBuffering}
                    error={playbackError}
                    onTogglePlayback={togglePlayback}
                    onSeek={seekPlayback}
                    onToggleMute={toggleMute}
                    onVolumeChange={setPlaybackVolume}
                  />
                )}
              </div>

              <aside className="min-h-0 border-t xl:border-t-0 xl:border-l border-slate-200 overflow-y-auto p-5 space-y-5">
                {(meeting.status === 'reviewing' || meeting.status === 'completed') && speakerStats.length > 0 && (
                  <section>
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">Speakers</h2>
                      <button
                        onClick={saveSpeakerNames}
                        disabled={isSavingSpeakers || isFinalizing}
                        title="Save speaker names"
                        className="inline-flex items-center justify-center rounded-md border border-slate-200 p-1.5 text-indigo-600 hover:bg-slate-50 disabled:opacity-50"
                      >
                        {isSavingSpeakers ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                      </button>
                    </div>
                    <div className="space-y-2">
                      {speakerStats.map((speaker) => (
                        <div key={speaker.label} className="rounded-md border border-slate-200 px-3 py-2">
                          <div className="mb-2 flex items-center justify-between gap-2 text-[10px] uppercase tracking-wide text-slate-500">
                            <span className="inline-flex items-center gap-2 font-mono">
                              <span className={cn('h-2 w-2 shrink-0 rounded-full', speakerStyle(speaker.label).swatch)} />
                              {speaker.label}
                            </span>
                            <span>{speaker.count} lines · {formatTime(speaker.seconds)}</span>
                          </div>
                          <input
                            value={speakerNames[speaker.label] ?? ''}
                            onChange={(event) => setSpeakerNames(prev => ({ ...prev, [speaker.label]: event.target.value }))}
                            placeholder={speaker.label}
                            className="w-full rounded-md px-2 py-1.5 text-sm"
                          />
                        </div>
                      ))}
                    </div>
                  </section>
                )}
                <section>
                  <h2 className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">Summary</h2>
                  <p className="text-sm leading-relaxed text-slate-200">
                    {meeting.summary?.summary || (meeting.status === 'ready' ? 'This raw recording has not been processed yet.' : meeting.status === 'reviewing' ? 'Finalize this meeting to generate a summary.' : meeting.status === 'completed' ? 'No summary generated.' : 'Summary appears after processing.')}
                  </p>
                </section>
                <section>
                  <h2 className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-500"><Gavel size={14} /> Decisions</h2>
                  <List values={meeting.summary?.decisions ?? []} empty="No decisions captured." />
                </section>
                <section>
                  <h2 className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-500"><ListChecks size={14} /> Action Items</h2>
                  {meeting.summary?.action_items?.length ? (
                    <div className="space-y-2">
                      {meeting.summary.action_items.map((item, index) => (
                        <div key={`${item.task}-${index}`} className="rounded-md border border-slate-200 px-3 py-2 text-sm text-slate-200">
                          <div>{item.task}</div>
                          <div className="mt-1 text-xs text-slate-500">
                            {item.owner || 'Unassigned'}{item.due ? ` · ${item.due}` : ''}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-slate-500">No action items captured.</p>
                  )}
                </section>
                <section>
                  <h2 className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-500"><CircleHelp size={14} /> Open Questions</h2>
                  <List values={meeting.summary?.open_questions ?? []} empty="No open questions captured." />
                </section>
              </aside>
            </div>
          </>
        ) : (
          <div className="h-full flex items-center justify-center text-slate-500">
            Upload or select a recording.
          </div>
        )}
      </div>
    </div>
  );
}

function ProcessingIndicator({ label, compact = false }: { label: string; compact?: boolean }) {
  return (
    <div className={cn(
      "shrink-0 border-b border-emerald-500/15 bg-emerald-950/20",
      compact ? "w-full max-w-md rounded-md border px-4 py-3" : "px-5 py-3"
    )}>
      <div className="mb-2 flex items-center gap-2 text-sm font-medium text-emerald-100">
        <Loader2 size={16} className="animate-spin text-emerald-300" />
        <span>{label}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-emerald-950/80">
        <div className="engram-progress-bar h-full w-1/3 rounded-full bg-emerald-400" />
      </div>
    </div>
  );
}

function TranscriptTurnRow({
  turn,
  canPlay,
  canEdit,
  isEditing,
  isActive,
  isSaving,
  onSeek,
  onEditingChange,
  onSave,
}: {
  turn: TranscriptTurn;
  canPlay: boolean;
  canEdit: boolean;
  isEditing: boolean;
  isActive: boolean;
  isSaving: boolean;
  onSeek: (seconds: number) => void;
  onEditingChange: (editing: boolean) => void;
  onSave: (texts: string[]) => Promise<boolean>;
}) {
  const [drafts, setDrafts] = useState(() => turn.segments.map(segment => segment.text));
  const style = turn.speaker ? speakerStyle(turn.speaker) : null;
  const hasEmptyDraft = drafts.some(text => !text.trim());
  const startEditing = () => {
    setDrafts(turn.segments.map(segment => segment.text));
    onEditingChange(true);
  };
  const cancelEditing = () => {
    setDrafts(turn.segments.map(segment => segment.text));
    onEditingChange(false);
  };
  const saveEditing = async () => {
    if (hasEmptyDraft || isSaving) return;
    if (await onSave(drafts)) onEditingChange(false);
  };
  const seekToTurn = () => {
    if (canPlay) onSeek(turn.startSeconds);
  };
  const seekFromMessage = (event: MouseEvent<HTMLDivElement>) => {
    if (isEditing) return;
    const target = event.target as HTMLElement;
    if (target.closest('button, input, textarea, select, a, [contenteditable="true"]')) return;
    const selection = window.getSelection();
    if (selection && !selection.isCollapsed) return;
    seekToTurn();
  };
  return (
    <div
      className="grid grid-cols-1 gap-2 py-4 sm:grid-cols-[8rem_minmax(0,1fr)] sm:gap-4"
      onClick={seekFromMessage}
    >
      <button
        type="button"
        onClick={seekToTurn}
        disabled={!canPlay}
        aria-label={`Seek to ${formatTime(turn.startSeconds)}`}
        aria-current={isActive ? 'true' : undefined}
        className="flex min-w-0 items-center gap-2 text-left disabled:cursor-default sm:items-start"
      >
        {turn.speaker && turn.speakerName && style ? (
          <>
            <span className={cn('flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-[11px] font-bold', style.avatar)}>
              {speakerInitials(turn.speakerName)}
            </span>
            <div className="min-w-0 pt-0.5">
              <div className="truncate text-xs font-semibold text-slate-200">{turn.speakerName}</div>
              <div className="mt-0.5 font-mono text-[10px] text-slate-500">
                {formatTime(turn.startSeconds)}-{formatTime(turn.endSeconds)}
              </div>
            </div>
          </>
        ) : (
          <span className="font-mono text-[10px] text-slate-500">
            {formatTime(turn.startSeconds)}-{formatTime(turn.endSeconds)}
          </span>
        )}
      </button>
      <div className="group relative min-w-0 border-l-2 border-slate-700/70 py-1 pl-4 pr-2">
        {isActive && <span className="pointer-events-none absolute -left-3 inset-y-0 w-0.5 rounded-full bg-slate-300 sm:-left-[9.75rem]" />}
        {isEditing ? (
          <div className="space-y-3">
            {turn.segments.map((segment, index) => (
              <label key={segment.id ?? segment.segment_index} className="block">
                {turn.segments.length > 1 && (
                  <span className="mb-1 block font-mono text-[10px] text-slate-500">
                    {formatTime(segment.start_seconds)}-{formatTime(segment.end_seconds)}
                  </span>
                )}
                <textarea
                  autoFocus={index === 0}
                  value={drafts[index]}
                  onChange={event => setDrafts(current => current.map((text, draftIndex) => draftIndex === index ? event.target.value : text))}
                  onKeyDown={event => {
                    if (event.key === 'Escape') cancelEditing();
                    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) saveEditing();
                  }}
                  rows={Math.min(6, Math.max(2, Math.ceil(drafts[index].length / 80)))}
                  className="w-full resize-y rounded-md border border-slate-600 bg-slate-950/70 px-3 py-2 text-sm leading-6 text-slate-100 outline-none focus:border-emerald-500"
                />
              </label>
            ))}
            {hasEmptyDraft && <p className="text-xs text-rose-300">Transcript text cannot be empty.</p>}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={cancelEditing}
                disabled={isSaving}
                title="Cancel editing"
                aria-label="Cancel editing"
                className="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-400 hover:bg-slate-800 hover:text-slate-100 disabled:opacity-50"
              >
                <X size={16} />
              </button>
              <button
                type="button"
                onClick={saveEditing}
                disabled={hasEmptyDraft || isSaving}
                title="Save transcript changes"
                aria-label="Save transcript changes"
                className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
              >
                {isSaving ? <Loader2 size={16} className="animate-spin" /> : <Check size={16} />}
              </button>
            </div>
          </div>
        ) : (
          <>
            <p className="pr-8 text-sm leading-7 text-slate-200">{turn.text}</p>
            {canEdit && (
              <button
                type="button"
                onClick={startEditing}
                title="Edit transcript"
                aria-label="Edit transcript"
                className="absolute right-0 top-0 inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 opacity-100 transition-opacity hover:bg-slate-800 hover:text-slate-100 focus:opacity-100 sm:opacity-0 sm:group-hover:opacity-100"
              >
                <Pencil size={14} />
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function AudioTransport({
  currentTime,
  duration,
  volume,
  isMuted,
  isPlaying,
  isBuffering,
  error,
  onTogglePlayback,
  onSeek,
  onToggleMute,
  onVolumeChange,
}: {
  currentTime: number;
  duration: number;
  volume: number;
  isMuted: boolean;
  isPlaying: boolean;
  isBuffering: boolean;
  error: string | null;
  onTogglePlayback: () => void;
  onSeek: (seconds: number) => void;
  onToggleMute: () => void;
  onVolumeChange: (volume: number) => void;
}) {
  return (
    <div className="shrink-0 border-t border-slate-200 bg-slate-950/55 px-4 py-3 backdrop-blur-md">
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          onClick={onTogglePlayback}
          title={isPlaying ? 'Pause' : 'Play'}
          aria-label={isPlaying ? 'Pause' : 'Play'}
          className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-emerald-600 text-white hover:bg-emerald-700"
        >
          {isBuffering ? <Loader2 size={16} className="animate-spin" /> : isPlaying ? <Pause size={16} /> : <Play size={16} />}
        </button>
        <span className="w-24 shrink-0 font-mono text-[11px] text-slate-400">
          {formatTime(currentTime)} / {formatTime(duration)}
        </span>
        <input
          type="range"
          min="0"
          max={Math.max(duration, 0)}
          step="0.05"
          value={Math.min(currentTime, duration || 0)}
          onChange={(event) => onSeek(Number(event.target.value))}
          disabled={duration <= 0}
          aria-label="Recording position"
          className="engram-audio-slider min-w-0 flex-1"
        />
        <button
          type="button"
          onClick={onToggleMute}
          title={isMuted ? 'Unmute' : 'Mute'}
          aria-label={isMuted ? 'Unmute' : 'Mute'}
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center text-slate-300 hover:text-emerald-300"
        >
          {isMuted || volume === 0 ? <VolumeX size={17} /> : <Volume2 size={17} />}
        </button>
        <input
          type="range"
          min="0"
          max="1"
          step="0.05"
          value={volume}
          onChange={(event) => onVolumeChange(Number(event.target.value))}
          aria-label="Volume"
          className="engram-audio-slider hidden w-20 shrink-0 sm:block"
        />
      </div>
      {error && <div className="mt-1 pl-12 text-xs text-rose-300">{error}</div>}
    </div>
  );
}

function List({ values, empty }: { values: string[]; empty: string }) {
  if (!values.length) return <p className="text-sm text-slate-500">{empty}</p>;
  return (
    <ul className="space-y-2 text-sm text-slate-200">
      {values.map((value, index) => (
        <li key={`${value}-${index}`} className="rounded-md border border-slate-200 px-3 py-2">
          {value}
        </li>
      ))}
    </ul>
  );
}
