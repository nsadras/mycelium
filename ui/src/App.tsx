import { useState, useEffect } from 'react';
import { Menu, History } from 'lucide-react';
import api, { type Session } from './lib/api';
import Chat from './components/Chat';
import Engram from './components/Engram';
import MemoryInspector from './components/MemoryInspector';
import WikiExplorer from './components/WikiExplorer';
import LogExplorer from './components/LogExplorer';
import Sidebar from './components/Sidebar';
import SporeBackground from './components/SporeBackground';
import type { InspectorTarget } from './components/memory-inspector/types';
import { idleStatus, type AssistantActivity, type AssistantStatus } from './lib/assistantStatus';

const memoryOperationStatus: Record<
  'build' | 'clear-memory' | 'clear-wiki',
  AssistantStatus
> = {
  build: { activity: 'building', label: 'Building Memory', detail: 'Extracting statements and updating wiki' },
  'clear-memory': { activity: 'building', label: 'Clearing', detail: 'Resetting memory store' },
  'clear-wiki': { activity: 'building', label: 'Clearing Wiki', detail: 'Resetting wiki index' },
};

function isMemoryActivity(activity: AssistantActivity) {
  return activity === 'building';
}

function App() {
  const [activeTab, setActiveTab] = useState<'chat' | 'engram' | 'memory' | 'wiki' | 'logs'>('chat');
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [runningMemoryOperation, setRunningMemoryOperation] = useState<string | null>(null);
  const [memoryRevision, setMemoryRevision] = useState(0);
  const [memoryTarget, setMemoryTarget] = useState<InspectorTarget | null>(null);
  const [assistantStatus, setAssistantStatus] = useState<AssistantStatus>(idleStatus);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sessionsOpen, setSessionsOpen] = useState(false);

  const selectPrimaryTab = (tab: 'chat' | 'engram' | 'memory' | 'wiki' | 'logs') => {
    if (tab === 'memory') setMemoryTarget(null);
    setActiveTab(tab);
  };

  useEffect(() => {
    const fetchSessions = async () => {
      try {
        const res = await api.get('/sessions/');
        const ordered = [...res.data].reverse();
        setSessions(ordered);
        if (ordered.length > 0) {
          setSelectedSessionId((current) => current ?? ordered[0].id);
        }
      } catch (err) {
        console.error("Failed to fetch sessions", err);
      }
    };

    void fetchSessions();
  }, []);

  const handleCreateSession = async (query?: string) => {
    try {
      const name = query?.trim() || "New session";
      const res = await api.post('/sessions/', { query: name });
      setSessions([res.data, ...sessions]);
      setSelectedSessionId(res.data.id);
      setActiveTab('chat');
    } catch (err) {
      console.error("Failed to create session", err);
    }
  };

  const handleRenameSession = async (id: string, query: string) => {
    const name = query.trim();
    if (!name) return;
    try {
      const res = await api.patch(`/sessions/${id}`, { query: name });
      setSessions(prev => prev.map(s => s.id === id ? { ...s, query: res.data.query } : s));
    } catch (err) {
      console.error("Failed to rename session", err);
    }
  };

  const handleBuildMemory = async () => {
    await handleMemoryOperation('build');
  };

  const handleMemoryOperation = async (
    operation: 'build' | 'clear-memory' | 'clear-wiki'
  ) => {
    let shouldResetStatus = true;
    try {
      if (operation === 'clear-memory') {
        const confirmed = window.confirm(
          'Delete all wiki pages and episodic logs? This is intended for development and cannot be undone.'
        );
        if (!confirmed) return;
      } else if (operation === 'clear-wiki') {
        const confirmed = window.confirm(
          'Delete all wiki pages? This will reset the wiki, but keep all daily event logs and chat sessions intact.'
        );
        if (!confirmed) return;
      }
      let res;
      setRunningMemoryOperation(operation);
      setAssistantStatus(memoryOperationStatus[operation]);

      if (operation === 'clear-memory') {
        res = await api.post('/memory/dev/clear');
      } else if (operation === 'clear-wiki') {
        res = await api.post('/memory/dev/clear-wiki');
      } else {
        res = await api.post('/memory/build');
      }
      setMemoryRevision((revision) => revision + 1);
      alert(`${operation.replaceAll('-', ' ')} complete:\n${JSON.stringify(res.data, null, 2)}`);
    } catch (err) {
      console.error("Memory operation failed", err);
      shouldResetStatus = false;
      setAssistantStatus({ activity: 'error', label: 'Operation failed', detail: 'Check backend logs' });
      window.setTimeout(() => setAssistantStatus(idleStatus), 2500);
      alert('Memory operation failed. Check the console and backend logs.');
    } finally {
      setRunningMemoryOperation(null);
      if (shouldResetStatus && isMemoryActivity(memoryOperationStatus[operation].activity)) {
        setAssistantStatus(idleStatus);
      }
    }
  };

  return (
    <div className="relative flex w-full h-dvh text-slate-100 overflow-hidden z-10">
      <SporeBackground />
      <Sidebar 
        activeTab={activeTab} 
        setActiveTab={selectPrimaryTab}
        onBuildMemory={handleBuildMemory}
        onMemoryOperation={handleMemoryOperation}
        runningMemoryOperation={runningMemoryOperation}
        assistantStatus={assistantStatus}
        isOpenMobile={sidebarOpen}
        onCloseMobile={() => setSidebarOpen(false)}
      />
      
      <main className="flex-1 flex flex-col min-w-0 h-full relative z-10">
        {/* Mobile top header bar */}
        <div className="flex md:hidden items-center justify-between p-4 bg-slate-900 border-b border-slate-800 text-white shrink-0">
          <button 
            onClick={() => setSidebarOpen(true)}
            className="p-1 hover:bg-slate-800 rounded-md text-emerald-400 cursor-pointer"
            title="Open Menu"
          >
            <Menu size={24} />
          </button>
          
          <div className="flex items-center gap-2">
            <span className="font-bold text-sm uppercase tracking-wider text-emerald-400">
              {activeTab}
            </span>
          </div>

          {activeTab === 'chat' ? (
            <button 
              onClick={() => setSessionsOpen(true)}
              className="p-1 hover:bg-slate-800 rounded-md text-emerald-400 cursor-pointer"
              title="Open Sessions"
            >
              <History size={24} />
            </button>
          ) : (
            <div className="w-8" />
          )}
        </div>

        {activeTab === 'chat' && (
          <Chat 
            sessions={sessions}
            selectedId={selectedSessionId}
            onSelect={(id) => {
              setSelectedSessionId(id);
              setSessionsOpen(false);
            }}
            onCreate={handleCreateSession}
            onRename={handleRenameSession}
            setAssistantStatus={setAssistantStatus}
            sessionsOpenMobile={sessionsOpen}
            onCloseSessionsMobile={() => setSessionsOpen(false)}
          />
        )}
        {activeTab === 'engram' && <Engram setAssistantStatus={setAssistantStatus} />}
        {activeTab === 'memory' && <MemoryInspector refreshKey={memoryRevision} target={memoryTarget} />}
        {activeTab === 'wiki' && <WikiExplorer onInspectReview={(proposalId) => { setMemoryTarget({ tab: 'reconsolidation', id: proposalId }); setActiveTab('memory'); }} />}
        {activeTab === 'logs' && <LogExplorer />}
      </main>
    </div>
  );
}

export default App;
