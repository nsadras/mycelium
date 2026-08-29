import { useState, type MouseEvent } from 'react';
import { Check, Loader2, Pause, Pencil, Play, Volume2, VolumeX, X } from 'lucide-react';

import { cn, formatTime, speakerInitials, speakerStyle, type TranscriptTurn } from './utils';

export function ProcessingIndicator({ label, compact = false }: { label: string; compact?: boolean }) {
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

export function TranscriptTurnRow({
  turn,
  canPlay,
  canEdit,
  isEditing,
  isActive,
  isSaving,
  speakerOptions,
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
  speakerOptions: { value: string; label: string }[];
  onSeek: (seconds: number) => void;
  onEditingChange: (editing: boolean) => void;
  onSave: (texts: string[], speaker: string) => Promise<boolean>;
}) {
  const [drafts, setDrafts] = useState(() => turn.segments.map(segment => segment.text));
  const [draftSpeaker, setDraftSpeaker] = useState(turn.speaker ?? '');
  const style = turn.speaker ? speakerStyle(turn.speaker) : null;
  const hasEmptyDraft = drafts.some(text => !text.trim());
  const startEditing = () => {
    setDrafts(turn.segments.map(segment => segment.text));
    setDraftSpeaker(turn.speaker ?? '');
    onEditingChange(true);
  };
  const cancelEditing = () => {
    setDrafts(turn.segments.map(segment => segment.text));
    setDraftSpeaker(turn.speaker ?? '');
    onEditingChange(false);
  };
  const saveEditing = async () => {
    if (hasEmptyDraft || isSaving) return;
    if (await onSave(drafts, draftSpeaker)) onEditingChange(false);
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
            {turn.speaker && (
              <label className="block">
                <span className="mb-1 block text-xs font-medium text-slate-400">Speaker</span>
                <select
                  value={draftSpeaker}
                  onChange={event => setDraftSpeaker(event.target.value)}
                  className="w-full rounded-md border border-slate-600 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 outline-none focus:border-emerald-500"
                >
                  {speakerOptions.map(option => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                  <option value="__new__">New speaker</option>
                </select>
              </label>
            )}
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
                    if (event.key === 'Escape') {
                      event.preventDefault();
                      cancelEditing();
                    }
                    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
                      event.preventDefault();
                      saveEditing();
                    }
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

export function AudioTransport({
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

export function List({ values, empty }: { values: string[]; empty: string }) {
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
