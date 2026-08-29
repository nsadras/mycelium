import { useCallback, useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import { AlertTriangle, CheckCircle2, CircleHelp, Clock, FileAudio, Gavel, ListChecks, Loader2, RotateCw, Save, Trash2, Upload } from 'lucide-react';
import api, { engramAudioUrl, type EngramMeeting } from '../lib/api';
import type { AssistantStatus } from '../lib/assistantStatus';
import {
  AudioTransport, List, ProcessingIndicator, TranscriptTurnRow,
} from './engram/presentation';
import {
  cn, formatTime, isBusyStatus, nextSpeakerLabel, processingLabel,
  speakerStyle, statusTone, transcriptTurns, type TranscriptTurn,
} from './engram/utils';

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

  const applyMeeting = useCallback((next: EngramMeeting | null) => {
    setMeeting(next);
    setSpeakerNames(next?.speaker_names ?? {});
  }, []);

  const selectMeeting = useCallback((id: string | null) => {
    setSelectedId(id);
    applyMeeting(null);
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
  }, [applyMeeting]);

  const refreshMeetings = useCallback(async () => {
    try {
      const res = await api.get('/engram/meetings');
      const next = res.data as EngramMeeting[];
      setMeetings(next);
      setSelectedId(current => current ?? next[0]?.id ?? null);
    } catch (err) {
      console.error('Failed to fetch meetings', err);
    }
  }, []);

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
    let cancelled = false;
    api.get('/engram/meetings')
      .then((res) => {
        if (cancelled) return;
        const next = res.data as EngramMeeting[];
        setMeetings(next);
        setSelectedId(current => current ?? next[0]?.id ?? null);
        setAssistantStatus({ activity: 'engram', label: 'Engram', detail: 'Ready for meetings' });
      })
      .catch((err) => console.error('Failed to fetch meetings', err));
    return () => { cancelled = true; };
  }, [setAssistantStatus]);

  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    api.get(`/engram/meetings/${selectedId}`)
      .then((res) => {
        if (cancelled) return;
        const next = res.data as EngramMeeting;
        applyMeeting(next);
        setMeetings(prev => prev.map(item => item.id === selectedId ? { ...item, ...next } : item));
      })
      .catch((err) => console.error('Failed to fetch meeting', err));
    return () => { cancelled = true; };
  }, [applyMeeting, selectedId]);

  useEffect(() => {
    if (!selectedId || meeting?.id !== selectedId || !isBusyStatus(meeting.status)) return;
    let cancelled = false;
    let pollTimer: ReturnType<typeof setTimeout> | null = null;

    const pollMeeting = async () => {
      try {
        const res = await api.get(`/engram/meetings/${selectedId}`);
        if (cancelled) return;
        const next = res.data as EngramMeeting;
        applyMeeting(next);
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
  }, [applyMeeting, selectedId, meeting?.id, meeting?.status, setAssistantStatus]);

  useEffect(() => {
    if (transcriptRef.current) {
      transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
    }
  }, [segments.length]);

  const processMeeting = async () => {
    if (!meeting || isProcessing) return;
    setIsProcessing(true);
    setAssistantStatus({ activity: 'thinking', label: 'Processing meeting', detail: meeting.title });
    try {
      const res = await api.post(`/engram/meetings/${meeting.id}/process`);
      applyMeeting(res.data);
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
      applyMeeting(res.data);
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

  const saveTranscriptTurn = async (turn: TranscriptTurn, texts: string[], selectedSpeaker: string) => {
    if (!meeting || savingTranscriptTurn || texts.length !== turn.segments.length) return false;
    const speaker = selectedSpeaker === '__new__'
      ? nextSpeakerLabel(speakerStats.map(item => item.label))
      : selectedSpeaker || null;
    const speakerChanged = speaker !== turn.speaker;
    const textChanged = turn.segments.some((segment, index) => texts[index].trim() !== segment.text);
    if (!speakerChanged && !textChanged) return true;

    const updates = turn.segments.flatMap((segment, index) => (
      segment.id !== null ? [{ id: segment.id, text: texts[index].trim() }] : []
    ));
    if (updates.length !== turn.segments.length) return false;

    setSavingTranscriptTurn(turn.key);
    try {
      const res = await api.put(`/engram/meetings/${meeting.id}/transcript`, {
        segments: updates,
        speaker: speakerChanged ? speaker : undefined,
      });
      applyMeeting(res.data);
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
      applyMeeting(res.data);
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
      const next = meetings.filter(item => item.id !== target.id);
      setMeetings(next);
      if (selectedId === target.id) selectMeeting(next[0]?.id ?? null);
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
      selectMeeting(res.data.id);
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
            <button onClick={refreshMeetings} title="Refresh meetings" className="p-1 hover:bg-slate-100 rounded-md text-indigo-600">
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
              onClick={() => selectMeeting(item.id)}
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
                        speakerOptions={speakerStats.map(speaker => ({
                          value: speaker.label,
                          label: speakerNames[speaker.label]?.trim()
                            ? `${speakerNames[speaker.label].trim()} (${speaker.label})`
                            : speaker.label,
                        }))}
                        onSeek={seekPlayback}
                        onEditingChange={editing => setEditingTranscriptTurn(editing ? turn.key : null)}
                        onSave={(texts, speaker) => saveTranscriptTurn(turn, texts, speaker)}
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
