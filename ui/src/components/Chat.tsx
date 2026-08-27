import { useState, useEffect, useMemo, useRef, memo, type Dispatch, type FormEvent, type SetStateAction } from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import { BookOpen, Check, ChevronDown, ChevronRight, Globe, Pencil, Send, Plus, History, X, Compass } from 'lucide-react';
import api, { type Session, type Message } from '../lib/api';
import type { AssistantStatus } from '../lib/assistantStatus';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import PromptNavigator from './PromptNavigator';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

function ToolEvents({ events }: { events: NonNullable<Message['tool_events']> }) {
  const [open, setOpen] = useState<Record<number, boolean>>({});

  return (
    <div className="mb-3 space-y-1.5 border-b border-slate-200 pb-2">
      {events.map((event, index) => {
        const isOpen = Boolean(open[index]);
        return (
          <div
            key={`${event.tool_name}-${index}`}
            className={cn(
              "rounded-md border bg-white text-xs",
              event.failed ? "border-rose-200" : "border-slate-200"
            )}
          >
            <button
              type="button"
              onClick={() => setOpen(prev => ({ ...prev, [index]: !isOpen }))}
              className="flex w-full items-center gap-2 px-2 py-1.5 text-left"
              title="Show tool call details"
            >
              {isOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
              <Globe size={13} className={event.failed ? "text-rose-500" : "text-indigo-500"} />
              <span className="font-semibold text-slate-700">{event.tool_name}</span>
              <span className={cn("ml-auto rounded px-1.5 py-0.5 text-[10px] font-semibold", event.failed ? "bg-rose-50 text-rose-700" : "bg-emerald-50 text-emerald-700")}>
                {event.failed ? "failed" : "ok"}
              </span>
            </button>
            {isOpen && (
              <div className="space-y-2 border-t border-slate-100 px-2 py-2">
                <div>
                  <div className="mb-1 font-semibold uppercase tracking-wide text-slate-400">Arguments</div>
                  <pre className="max-h-40 overflow-auto rounded bg-slate-50 p-2 text-[11px] leading-relaxed text-slate-700">
                    {JSON.stringify(event.arguments, null, 2)}
                  </pre>
                </div>
                <div>
                  <div className="mb-1 flex items-center gap-2 font-semibold uppercase tracking-wide text-slate-400">
                    Result
                    {event.truncated && <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-700">truncated</span>}
                  </div>
                  <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-2 text-[11px] leading-relaxed text-slate-700">
                    {event.result || "(empty result)"}
                  </pre>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

const ChatMessageItem = memo(function ChatMessageItem({ m, id }: { m: Message; id?: string }) {
  return (
    <div id={id} className={cn("flex", m.role === 'user' ? "justify-end" : "justify-start")}>
      <div className={cn(
        "max-w-[85%] rounded-2xl px-4 py-3 text-sm shadow-sm",
        m.role === 'user' 
          ? "bg-indigo-600 text-white rounded-br-none" 
          : "bg-slate-100 text-slate-800 rounded-bl-none"
      )}>
        <div className="font-bold text-[10px] uppercase mb-1 opacity-70">
          {m.role}
        </div>
        {m.role === 'user' ? (
          <div className="whitespace-pre-wrap leading-relaxed">{m.content}</div>
        ) : (
          <>
            {m.loaded_pages && m.loaded_pages.length > 0 && (
              <div className="mb-3 flex flex-wrap gap-1.5 border-b border-slate-200 pb-2">
                {m.loaded_pages.map((page) => (
                  <span
                    key={page.slug}
                    title={`${page.slug} v${page.version}`}
                    className="inline-flex items-center gap-1 rounded bg-white px-2 py-1 text-[10px] font-semibold text-indigo-600 ring-1 ring-indigo-100"
                  >
                    <BookOpen size={11} />
                    {page.title}
                  </span>
                ))}
              </div>
            )}
            {m.tool_events && m.tool_events.length > 0 && (
              <ToolEvents events={m.tool_events} />
            )}
            <div className="prose prose-sm prose-slate max-w-none prose-chat overflow-hidden">
              <ReactMarkdown 
                remarkPlugins={[remarkGfm, remarkMath]} 
                rehypePlugins={[rehypeKatex]}
                components={{
                  table: (componentProps) => {
                    const tableProps = { ...componentProps };
                    delete tableProps.node;
                    return (
                      <div className="overflow-x-auto max-w-full my-4 rounded-lg border border-slate-700/40">
                        <table className="min-w-full divide-y divide-slate-800" {...tableProps} />
                      </div>
                    );
                  }
                }}
              >
                {m.content}
              </ReactMarkdown>
            </div>
          </>
        )}
      </div>
    </div>
  );
});

interface ChatProps {
  sessions: Session[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onCreate: (query?: string) => void;
  onRename: (id: string, query: string) => void;
  setAssistantStatus: Dispatch<SetStateAction<AssistantStatus>>;
  sessionsOpenMobile?: boolean;
  onCloseSessionsMobile?: () => void;
}

export default function Chat({
  sessions,
  selectedId,
  onSelect,
  onCreate,
  onRename,
  setAssistantStatus,
  sessionsOpenMobile = false,
  onCloseSessionsMobile,
}: ChatProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);

  const [activePromptIndex, setActivePromptIndex] = useState<number | null>(null);
  const [navOpenMobile, setNavOpenMobile] = useState(false);

  const userPrompts = useMemo(
    () => messages
      .map((m, index) => ({ ...m, originalIndex: index }))
      .filter(m => m.role === 'user'),
    [messages],
  );

  const showNav = userPrompts.length >= 5;

  useEffect(() => {
    const container = scrollRef.current;
    if (!container || !showNav) return;

    const handleScroll = () => {
      let currentActive: number | null = null;
      let minDistance = Infinity;

      userPrompts.forEach((prompt) => {
        const el = document.getElementById(`msg-${prompt.originalIndex}`);
        if (el) {
          const rect = el.getBoundingClientRect();
          const containerRect = container.getBoundingClientRect();
          
          // Calculate distance from the top of the container
          const distance = Math.abs(rect.top - containerRect.top);
          if (distance < minDistance) {
            minDistance = distance;
            currentActive = prompt.originalIndex;
          }
        }
      });

      if (currentActive !== null) {
        setActivePromptIndex(currentActive);
      }
    };

    container.addEventListener('scroll', handleScroll);
    handleScroll();

    return () => {
      container.removeEventListener('scroll', handleScroll);
    };
  }, [showNav, userPrompts]);

  const handleJumpToPrompt = (msgIndex: number) => {
    const el = document.getElementById(`msg-${msgIndex}`);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      setActivePromptIndex(msgIndex);
    }
  };

  useEffect(() => {
    let cancelled = false;
    const loadHistory = selectedId
      ? api.get(`/sessions/${selectedId}`).then((res) => res.data.transcript as Message[])
      : Promise.resolve([] as Message[]);
    loadHistory
      .then((transcript) => {
        if (cancelled) return;
        setMessages(transcript);
        setAssistantStatus({ activity: 'idle', label: 'Idle', detail: selectedId ? 'Ready' : 'Select a session' });
        setNavOpenMobile(false);
      })
      .catch((err) => console.error("Failed to fetch history", err));
    return () => { cancelled = true; };
  }, [selectedId, setAssistantStatus]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = async (e: FormEvent) => {
    e.preventDefault();
    if (!input.trim() || !selectedId || isLoading) return;

    const optimisticTimestamp = new Date().toISOString();
    const userMsg: Message = { role: 'user', content: input, timestamp: optimisticTimestamp };
    setMessages([...messages, userMsg]);
    setInput('');
    setIsLoading(true);
    setAssistantStatus({ activity: 'thinking', label: 'Thinking', detail: 'Calling model' });
    let shouldResetStatus = true;

    try {
      const res = await api.post(`/sessions/${selectedId}/chat`, { message: input });
      if (res.data.tool_events?.length > 0) {
        setAssistantStatus({ activity: 'tool_calling', label: 'Tool calls complete', detail: `${res.data.tool_events.length} result${res.data.tool_events.length === 1 ? '' : 's'}` });
      } else {
        setAssistantStatus({ activity: 'responding', label: 'Responding', detail: 'Rendering reply' });
      }
      setMessages(prev => [
        ...prev.map(message => (
          message.role === 'user' && message.timestamp === optimisticTimestamp
            ? { ...message, timestamp: res.data.user_timestamp }
            : message
        )),
        {
          role: 'assistant',
          content: res.data.response,
          timestamp: res.data.assistant_timestamp,
          loaded_pages: res.data.loaded_pages,
          tool_events: res.data.tool_events,
        },
      ]);
    } catch (err) {
      console.error("Chat error", err);
      shouldResetStatus = false;
      setAssistantStatus({ activity: 'error', label: 'Chat failed', detail: 'Check backend logs' });
      window.setTimeout(() => {
        setAssistantStatus({ activity: 'idle', label: 'Idle', detail: 'Ready' });
      }, 2500);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: "Error: Failed to get response from agent.",
        timestamp: new Date().toISOString(),
      }]);
    } finally {
      setIsLoading(false);
      if (shouldResetStatus) {
        window.setTimeout(() => {
          setAssistantStatus({ activity: 'idle', label: 'Idle', detail: 'Ready' });
        }, 900);
      }
    }
  };

  const handleCreate = () => {
    const name = window.prompt('Name this chat session:', 'New session');
    if (name === null) return;
    onCreate(name);
  };

  const startRename = (session: Session) => {
    setEditingSessionId(session.id);
    setEditingName(session.query);
  };

  const submitRename = () => {
    if (!editingSessionId) return;
    onRename(editingSessionId, editingName);
    setEditingSessionId(null);
    setEditingName('');
  };

  return (
    <div className="flex flex-1 min-w-0 min-h-0 relative">
      {/* Mobile backdrop for Session list */}
      {sessionsOpenMobile && (
        <div 
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-30 md:hidden"
          onClick={onCloseSessionsMobile}
        />
      )}
      {/* Session History Sidebar */}
      <div 
        className={cn(
          "bg-white border-r border-slate-200 flex flex-col shrink-0 transition-transform duration-300 z-40 md:z-auto",
          // Desktop styling
          "md:translate-x-0 md:static md:w-64 md:h-full md:flex",
          // Mobile styling: overlay slide-in drawer
          "fixed top-0 left-0 h-full w-64 shadow-2xl",
          sessionsOpenMobile ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="p-4 flex items-center justify-between border-b border-slate-200">
          <h2 className="font-semibold text-slate-700 flex items-center gap-2">
            <History size={16} /> Sessions
          </h2>
          <button onClick={handleCreate} title="New session" className="p-1 hover:bg-slate-100 rounded-md text-indigo-600 transition-colors">
            <Plus size={20} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {sessions.map((s) => (
            <div
              key={s.id}
              className={cn(
                "group flex items-center gap-1 rounded-md text-sm transition-colors",
                selectedId === s.id ? "bg-indigo-50 text-indigo-700 font-medium" : "hover:bg-slate-50 text-slate-600"
              )}
            >
              {editingSessionId === s.id ? (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    submitRename();
                  }}
                  className="flex min-w-0 flex-1 items-center gap-1 px-2 py-1.5"
                >
                  <input
                    value={editingName}
                    onChange={(e) => setEditingName(e.target.value)}
                    className="min-w-0 flex-1 rounded border border-indigo-200 bg-white px-2 py-1 text-sm text-slate-800 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    autoFocus
                  />
                  <button type="submit" title="Save name" className="p-1 text-emerald-600 hover:bg-emerald-50 rounded">
                    <Check size={14} />
                  </button>
                  <button
                    type="button"
                    title="Cancel"
                    onClick={() => setEditingSessionId(null)}
                    className="p-1 text-slate-400 hover:bg-slate-100 rounded"
                  >
                    <X size={14} />
                  </button>
                </form>
              ) : (
                <>
                  <button
                    onClick={() => onSelect(s.id)}
                    className="min-w-0 flex-1 text-left px-3 py-2 truncate"
                    title={s.query}
                  >
                    {s.query}
                  </button>
                  <button
                    onClick={() => startRename(s)}
                    title="Rename session"
                    className="mr-1 p-1 text-slate-400 opacity-0 transition-opacity hover:bg-slate-100 hover:text-indigo-600 rounded group-hover:opacity-100"
                  >
                    <Pencil size={14} />
                  </button>
                </>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0 bg-white relative">
        <div 
          className={cn(
            "flex-1 overflow-y-auto px-3 py-6 space-y-6 md:pl-6",
            showNav ? "md:pr-20" : "md:pr-6"
          )} 
          ref={scrollRef}
        >
          {messages.length === 0 ? (
            <div className="h-full flex items-center justify-center text-slate-400">
              {selectedId ? "Start the conversation..." : "Select or create a session to start."}
            </div>
          ) : (
            messages.map((m, i) => (
              <ChatMessageItem key={i} m={m} id={m.role === 'user' ? `msg-${i}` : undefined} />
            ))
          )}
          {isLoading && (
            <div className="flex justify-start">
              <div className="bg-slate-100 text-slate-800 rounded-2xl rounded-bl-none px-4 py-3 text-sm shadow-sm flex gap-1">
                <div className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" />
                <div className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce [animation-delay:0.2s]" />
                <div className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce [animation-delay:0.4s]" />
              </div>
            </div>
          )}
        </div>

        {showNav && (
          <>
            {/* Desktop Navigation stack (hidden on mobile) */}
            <PromptNavigator
              userPrompts={userPrompts}
              activePromptIndex={activePromptIndex}
              onJumpToPrompt={handleJumpToPrompt}
            />

            {/* Mobile Navigation float trigger button */}
            <button
              type="button"
              onClick={() => setNavOpenMobile(true)}
              className="md:hidden fixed right-3 bottom-24 w-10 h-10 rounded-full bg-slate-900/90 border border-emerald-500/30 text-emerald-400 flex items-center justify-center shadow-lg hover:bg-slate-800 transition-colors z-20 cursor-pointer active:scale-95"
              title="Thread Navigation"
            >
              <Compass size={20} />
            </button>

            {/* Mobile Navigation overlay drawer */}
            {navOpenMobile && (
              <PromptNavigator
                userPrompts={userPrompts}
                activePromptIndex={activePromptIndex}
                onJumpToPrompt={(idx) => {
                  handleJumpToPrompt(idx);
                  setNavOpenMobile(false);
                }}
                isMobileView={true}
                onCloseMobile={() => setNavOpenMobile(false)}
              />
            )}
          </>
        )}

        <form onSubmit={handleSend} className="p-3 md:p-6 border-t border-slate-200">
          <div className="relative">
            <input
              type="text"
              value={input}
              onChange={(e) => {
                const nextValue = e.target.value;
                setInput(nextValue);
                if (!isLoading) {
                  setAssistantStatus(prev => {
                    const isNextEmpty = !nextValue.trim();
                    const nextActivity = isNextEmpty ? 'idle' : 'listening';
                    if (prev.activity === nextActivity) {
                      return prev;
                    }
                    return isNextEmpty
                      ? { activity: 'idle', label: 'Idle', detail: selectedId ? 'Ready' : 'Select a session' }
                      : { activity: 'listening', label: 'Listening', detail: 'Composing' };
                  });
                }
              }}
              placeholder={selectedId ? "Send a message..." : "Select a session first"}
              disabled={!selectedId || isLoading}
              className="w-full bg-slate-100 border-none rounded-xl pl-4 pr-12 py-3 focus:ring-2 focus:ring-indigo-500 disabled:opacity-50 transition-all shadow-inner"
            />
            <button
              type="submit"
              disabled={!selectedId || !input.trim() || isLoading}
              className="absolute right-2 top-1.5 p-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:hover:bg-indigo-600 transition-colors shadow-md"
            >
              <Send size={18} />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
