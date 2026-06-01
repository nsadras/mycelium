import { Archive, Book, BrainCircuit, FileText, Loader2, MessageSquare, Moon, RefreshCw, Save, Sparkles, Trash2 } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import Avatar from './Avatar';
import type { AssistantStatus } from '../lib/assistantStatus';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface SidebarProps {
  activeTab: 'chat' | 'wiki' | 'logs';
  setActiveTab: (tab: 'chat' | 'wiki' | 'logs') => void;
  onDream: () => void;
  onMemoryOperation: (
    operation: 'flush-current' | 'flush-idle' | 'flush-all' | 'reconsolidate-current' | 'dream' | 'decay' | 'clear-memory' | 'clear-wiki'
  ) => void;
  hasSelectedSession: boolean;
  runningMemoryOperation: string | null;
  assistantStatus: AssistantStatus;
}

export default function Sidebar({
  activeTab,
  setActiveTab,
  onDream,
  onMemoryOperation,
  hasSelectedSession,
  runningMemoryOperation,
  assistantStatus,
}: SidebarProps) {
  const tabs = [
    { id: 'chat', label: 'Chat', icon: MessageSquare },
    { id: 'wiki', label: 'Wiki', icon: Book },
    { id: 'logs', label: 'Logs', icon: FileText },
  ] as const;

  const memoryOps = [
    {
      id: 'flush-current',
      label: 'Flush Current',
      icon: Save,
      needsSession: true,
      tooltip: 'Encode the selected chat episode into episodic memory.',
    },
    {
      id: 'flush-idle',
      label: 'Flush Idle',
      icon: RefreshCw,
      needsSession: false,
      tooltip: 'Encode episodes that are idle or have grown large.',
    },
    {
      id: 'flush-all',
      label: 'Flush All',
      icon: Archive,
      needsSession: false,
      tooltip: 'Encode every active chat episode now.',
    },
    {
      id: 'reconsolidate-current',
      label: 'Resolve Current',
      icon: BrainCircuit,
      needsSession: true,
      tooltip: 'Apply pending reconsolidation updates for the selected chat.',
    },
    {
      id: 'decay',
      label: 'Decay Pass',
      icon: RefreshCw,
      needsSession: false,
      tooltip: 'Recompute decay scores and archive weak memories.',
    },
    {
      id: 'clear-wiki',
      label: 'Clear Wiki Pages',
      icon: Trash2,
      needsSession: false,
      tooltip: 'Delete all wiki pages but keep all episodic logs and sessions intact.',
    },
    {
      id: 'clear-memory',
      label: 'Clear Memory',
      icon: Trash2,
      needsSession: false,
      tooltip: 'Delete all wiki pages and episodic logs for development.',
    },
  ] as const;

  return (
    <aside className="w-64 bg-slate-900 text-slate-300 flex flex-col">
      <div className="p-6 flex items-center gap-3">
        <div className="w-8 h-8 bg-emerald-500/10 border border-emerald-500/20 rounded-lg flex items-center justify-center text-emerald-400 shadow-[0_0_10px_rgba(16,185,129,0.15)]">
          <svg
            viewBox="14 10 132 132"
            className="w-5 h-5 fill-current"
            xmlns="http://www.w3.org/2000/svg"
            aria-hidden="true"
          >
            <path d="M 50,75 C 50,110 56,128 65,128 C 72,128 74,120 80,120 C 86,120 88,128 95,128 C 104,128 110,110 110,75 Z" />
            <path d="M 20,70 C 20,32 45,18 80,18 C 115,18 140,32 140,70 C 140,84 115,88 80,88 C 45,88 20,84 20,70 Z" />
          </svg>
        </div>
        <h1 className="text-xl font-bold text-white tracking-tight">Mycelium</h1>
      </div>

      <Avatar status={assistantStatus} activeTab={activeTab} />

      <nav className="flex-1 px-4 space-y-1">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
              activeTab === tab.id 
                ? "bg-slate-800 text-white" 
                : "hover:bg-slate-800 hover:text-white"
            )}
          >
            <tab.icon size={18} />
            {tab.label}
          </button>
        ))}
      </nav>

      <div className="p-4 mt-auto space-y-2 border-t border-slate-800">
        <div className="px-1 pb-1 text-[10px] font-bold uppercase tracking-wider text-slate-500">
          Memory Operations
        </div>
        {memoryOps.map((op) => {
          const Icon = op.icon;
          const isRunning = runningMemoryOperation === op.id;
          const anyRunning = runningMemoryOperation !== null;
          const disabled = (op.needsSession && !hasSelectedSession) || anyRunning;
          return (
            <button
              key={op.id}
              onClick={() => onMemoryOperation(op.id)}
              disabled={disabled}
              title={disabled ? 'Select a chat session first.' : op.tooltip}
              className={cn(
                "w-full flex items-center gap-2 px-3 py-2 rounded-md text-xs font-semibold transition-colors",
                disabled
                  ? "text-slate-600 cursor-not-allowed"
                  : op.id === 'clear-memory'
                    ? "text-rose-300 hover:bg-rose-950/50 hover:text-rose-100"
                    : "text-slate-300 hover:bg-slate-800 hover:text-white"
              )}
            >
              {isRunning ? <Loader2 size={15} className="animate-spin" /> : <Icon size={15} />}
              {op.label}
            </button>
          );
        })}
        <button
          onClick={onDream}
          disabled={runningMemoryOperation !== null}
          title="Consolidate encoded episodic logs into wiki memory."
          className={cn(
            "w-full flex items-center justify-center gap-2 py-3 rounded-lg font-semibold transition-all shadow-lg shadow-indigo-500/20 active:scale-95",
            runningMemoryOperation
              ? "bg-indigo-900 text-indigo-200 cursor-wait"
              : "bg-indigo-600 hover:bg-indigo-700 text-white"
          )}
        >
          {runningMemoryOperation === 'dream' ? <Loader2 size={18} className="animate-spin" /> : <Moon size={18} />}
          Dream
        </button>
      </div>
    </aside>
  );
}
