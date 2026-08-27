import { useState, useEffect } from 'react';
import api from '../lib/api';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { FileText, Calendar } from 'lucide-react';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export default function LogExplorer() {
  const [logs, setLogs] = useState<string[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [content, setContent] = useState('');
  const [isUnconsolidating, setIsUnconsolidating] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.get('/memory/logs')
      .then((res) => {
        if (cancelled) return;
        setLogs(res.data);
        setSelectedFile(current => current ?? res.data[0] ?? null);
      })
      .catch((err) => console.error("Failed to fetch logs", err));
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!selectedFile) return;
    let cancelled = false;
    api.get(`/memory/logs/${selectedFile}`)
      .then((res) => {
        if (!cancelled) setContent(res.data.content);
      })
      .catch((err) => console.error("Failed to fetch log content", err));
    return () => { cancelled = true; };
  }, [selectedFile]);

  const handleUnconsolidate = async () => {
    if (!selectedFile || isUnconsolidating) return;
    const confirmed = window.confirm(
      `Mark all events in ${selectedFile.replace('.md', '')} as unconsolidated? This lets you re-run the Dream Pass for this day.`
    );
    if (!confirmed) return;
    
    setIsUnconsolidating(true);
    try {
      const res = await api.post(`/memory/logs/${selectedFile}/unconsolidate`);
      setContent(res.data.content);
      alert(`Success: Daily log ${selectedFile.replace('.md', '')} marked as unconsolidated.`);
    } catch (err) {
      console.error("Failed to unconsolidate log file", err);
      alert("Failed to mark log file as unconsolidated. Please check the backend logs.");
    } finally {
      setIsUnconsolidating(false);
    }
  };

  return (
    <div className="flex flex-col md:flex-row flex-1 min-h-0 min-w-0">
      <div className="w-full md:w-64 h-48 md:h-full bg-white border-b md:border-b-0 md:border-r border-slate-200 flex flex-col shrink-0">
        <div className="p-4 border-b border-slate-200">
          <h2 className="font-semibold text-slate-700 flex items-center gap-2">
            <Calendar size={16} /> Daily Logs
          </h2>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {logs.map((f) => (
            <button
              key={f}
              onClick={() => setSelectedFile(f)}
              className={cn(
                "w-full text-left px-3 py-2 rounded-md text-sm transition-colors flex items-center gap-2",
                selectedFile === f ? "bg-indigo-50 text-indigo-700 font-medium" : "hover:bg-slate-50 text-slate-600"
              )}
            >
              <FileText size={14} />
              {f.replace('.md', '')}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 min-h-0 bg-slate-900 overflow-hidden flex flex-col">
        {selectedFile ? (
          <div className="flex-1 min-h-0 flex flex-col">
            <div className="shrink-0 bg-slate-800 px-4 py-2 text-[10px] font-mono text-slate-400 flex items-center justify-between">
              <span className="font-semibold text-white">{selectedFile}</span>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={handleUnconsolidate}
                  disabled={isUnconsolidating}
                  className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-sans text-[10px] font-bold rounded transition-all shadow-[0_0_8px_rgba(16,185,129,0.25)] active:scale-95 cursor-pointer"
                  title="Mark all events in this log file as unconsolidated to re-run dream pass"
                >
                  {isUnconsolidating ? "Working..." : "Mark Unconsolidated"}
                </button>
                <span>EPISODIC LOG</span>
              </div>
            </div>
            <pre className="flex-1 min-h-0 overflow-auto p-6 text-indigo-300 font-mono text-sm leading-relaxed whitespace-pre-wrap">
              {content}
            </pre>
          </div>
        ) : (
          <div className="h-full flex items-center justify-center text-slate-600">
            No logs available.
          </div>
        )}
      </div>
    </div>
  );
}
