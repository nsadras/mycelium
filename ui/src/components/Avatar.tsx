import { useState } from 'react';
import { Settings, X } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import type { AssistantActivity, AssistantStatus } from '../lib/assistantStatus';
import { avatarsRegistry } from './avatars';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const activityCopy: Record<AssistantActivity, { label: string; detail: string }> = {
  idle: { label: 'Idle', detail: 'Ready' },
  listening: { label: 'Listening', detail: 'Composing' },
  thinking: { label: 'Thinking', detail: 'Calling model' },
  tool_calling: { label: 'Searching', detail: 'Using tools' },
  responding: { label: 'Responding', detail: 'Writing' },
  flushing: { label: 'Flushing', detail: 'Encoding episode' },
  dreaming: { label: 'Dreaming', detail: 'Consolidating logs' },
  reconsolidating: { label: 'Resolving', detail: 'Updating memory' },
  error: { label: 'Error', detail: 'Check logs' },
  clicked: { label: 'Hello', detail: 'Interacting' },
  'clicked-left': { label: 'Hello', detail: 'Interacting' },
  'clicked-right': { label: 'Hello', detail: 'Interacting' },
  wiki: { label: 'Wiki', detail: 'Browsing memory' },
  logs: { label: 'Logs', detail: 'Inspecting episodes' },
  engram: { label: 'Engram', detail: 'Meeting memory' },
  chat: { label: 'Chat', detail: 'Ready' },
};

export default function Avatar({ status, activeTab }: { status: AssistantStatus; activeTab?: 'chat' | 'engram' | 'wiki' | 'logs' }) {
  const [selectedAvatarId, setSelectedAvatarId] = useState<string>(() => {
    try {
      return localStorage.getItem('mycellium_avatar') || 'myco';
    } catch {
      return 'myco';
    }
  });
  const [showStateText, setShowStateText] = useState<boolean>(() => {
    try {
      return localStorage.getItem('mycellium_avatar_show_state') === 'true';
    } catch {
      return false;
    }
  });
  const [showSelector, setShowSelector] = useState(false);
  const [clickActivity, setClickActivity] = useState<AssistantActivity | null>(null);

  const handleAvatarClick = () => {
    if (clickActivity) return;
    const randomDir = Math.random() < 0.5 ? 'clicked-left' : 'clicked-right';
    setClickActivity(randomDir);
    setTimeout(() => {
      setClickActivity(null);
    }, 800);
  };

  const copy = activityCopy[status.activity];
  const label = status.label ?? copy.label;
  const detail = status.detail ?? copy.detail;

  // Find the selected avatar definition
  const avatarDef = avatarsRegistry.find(a => a.id === selectedAvatarId) || avatarsRegistry[0];
  const AvatarComponent = avatarDef.Component;

  const handleSelectAvatar = (id: string) => {
    setSelectedAvatarId(id);
    setShowSelector(false);
    try {
      localStorage.setItem('mycellium_avatar', id);
    } catch (err) {
      console.error('Failed to save avatar choice to localStorage', err);
    }
  };

  const handleToggleStateText = () => {
    const nextVal = !showStateText;
    setShowStateText(nextVal);
    try {
      localStorage.setItem('mycellium_avatar_show_state', String(nextVal));
    } catch (err) {
      console.error('Failed to save state text preference', err);
    }
  };

  return (
    <div
      className={cn(
        "group relative mx-4 mb-4 rounded-xl border p-3.5 transition-all duration-300 overflow-hidden",
        status.activity === 'error'
          ? "border-rose-900/60 bg-rose-950/20 shadow-lg shadow-rose-950/25"
          : "border-slate-800/80 bg-slate-950/20"
      )}
      aria-live="polite"
    >
      {/* Settings gear toggle button - visible on panel hover */}
      {!showSelector && (
        <button
          type="button"
          onClick={() => setShowSelector(true)}
          title="Change avatar settings..."
          className="absolute right-2 top-2 p-1 rounded-md text-slate-500 hover:text-white hover:bg-slate-800/80 transition-all opacity-0 group-hover:opacity-100 duration-200 z-10"
        >
          <Settings size={15} />
        </button>
      )}

      {showSelector ? (
        /* Selector overlay view (vertical list with descriptions + debug toggle) */
        <div className="flex flex-col items-center justify-between w-full min-h-[140px] py-1 relative">
          <div className="flex items-center justify-between w-full mb-3">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Select Avatar</span>
            <button
              type="button"
              onClick={() => setShowSelector(false)}
              className="p-1 rounded text-slate-500 hover:text-white hover:bg-slate-800 transition-colors"
            >
              <X size={14} />
            </button>
          </div>
          
          <div className="flex flex-col gap-2 w-full">
            {avatarsRegistry.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => handleSelectAvatar(item.id)}
                className={cn(
                  "w-full px-3 py-2 rounded-lg text-xs font-bold transition-all border text-left flex flex-col gap-0.5",
                  item.id === selectedAvatarId
                    ? "bg-indigo-600 border-indigo-500 text-white shadow-md shadow-indigo-600/10"
                    : "bg-slate-900 border-slate-800 text-slate-400 hover:text-white hover:border-slate-700"
                )}
              >
                <span className="font-bold">{item.name}</span>
                <span className={cn("text-[10px] font-normal", item.id === selectedAvatarId ? "text-indigo-200" : "text-slate-500")}>
                  {item.description}
                </span>
              </button>
            ))}
          </div>

          <div className="flex items-center justify-between w-full mt-3.5 pt-3 border-t border-slate-800/80">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Show State Info</span>
            <button
              type="button"
              onClick={handleToggleStateText}
              className={cn(
                "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none",
                showStateText ? "bg-indigo-600" : "bg-slate-800"
              )}
              aria-label="Toggle mascot state details"
            >
              <span
                className={cn(
                  "pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out",
                  showStateText ? "translate-x-4" : "translate-x-0"
                )}
              />
            </button>
          </div>
        </div>
      ) : (
        /* Display avatar and status details vertically (centered) */
        <div className="flex flex-col items-center gap-3">
          <div
            onClick={handleAvatarClick}
            className={cn(
              "relative flex h-40 w-40 shrink-0 items-center justify-center cursor-pointer active:scale-95 transition-transform duration-200",
              clickActivity && "pointer-events-none"
            )}
            title="Click me!"
          >
            <span className="relative w-full h-full flex items-center justify-center">
              <AvatarComponent activity={clickActivity || (status.activity === 'idle' ? (activeTab || 'chat') : status.activity)} status={status} />
            </span>
          </div>
          
          {showStateText && (
            <div className="w-full text-center mt-1 animate-fade-in">
              <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-0.5">
                Mascot State
              </div>
              <div className="text-base font-extrabold text-white leading-tight mb-1">
                {label}
              </div>
              <div className="text-xs text-slate-400 leading-normal px-2">
                {detail}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
