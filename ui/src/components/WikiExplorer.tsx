import { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import { Search, Tag, Clock, ShieldCheck, ChevronRight, Book, History as HistoryIcon, Pencil, Save, X, Trash2 } from 'lucide-react';
import api, { type WikiPage } from '../lib/api';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export default function WikiExplorer() {
  const [pages, setPages] = useState<WikiPage[]>([]);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [pageData, setPageData] = useState<WikiPage | null>(null);
  const [search, setSearch] = useState('');
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [editTitle, setEditTitle] = useState('');
  const [editTags, setEditTags] = useState('');
  const [editConfidence, setEditConfidence] = useState('0.5');
  const [editImportance, setEditImportance] = useState('0.5');
  const [editPinned, setEditPinned] = useState(false);
  const [editContent, setEditContent] = useState('');

  useEffect(() => {
    fetchPages();
  }, []);

  useEffect(() => {
    if (selectedSlug) {
      fetchPage(selectedSlug);
    }
  }, [selectedSlug]);

  const fetchPages = async () => {
    try {
      const res = await api.get('/memory/wiki');
      setPages(res.data);
    } catch (err) {
      console.error("Failed to fetch wiki pages", err);
    }
  };

  const fetchPage = async (slug: string) => {
    try {
      const res = await api.get(`/memory/wiki/${slug}`);
      setPageData(res.data);
      setIsEditing(false);
    } catch (err) {
      console.error("Failed to fetch page", err);
    }
  };

  const startEdit = () => {
    if (!pageData) return;
    setEditTitle(pageData.title);
    setEditTags(pageData.tags.join(', '));
    setEditConfidence(String(pageData.confidence ?? 0.5));
    setEditImportance(String(pageData.importance ?? 0.5));
    setEditPinned(Boolean(pageData.pinned));
    setEditContent(pageData.content || '');
    setIsEditing(true);
  };

  const saveEdit = async () => {
    if (!pageData) return;
    setIsSaving(true);
    try {
      const res = await api.put(`/memory/wiki/${pageData.slug}`, {
        title: editTitle,
        content: editContent,
        tags: editTags.split(',').map(t => t.trim()).filter(Boolean),
        confidence: Number(editConfidence),
        importance: Number(editImportance),
        pinned: editPinned,
      });
      setPageData(res.data);
      setPages(prev => prev.map(p => p.slug === res.data.slug ? { ...p, ...res.data } : p));
      setIsEditing(false);
    } catch (err) {
      console.error("Failed to save wiki page", err);
      alert("Failed to save wiki page.");
    } finally {
      setIsSaving(false);
    }
  };

  const handleDeletePage = async () => {
    if (!pageData) return;
    const confirmed = window.confirm(
      `Are you sure you want to delete the wiki page "${pageData.title}"? This will archive the page and remove it from the index.`
    );
    if (!confirmed) return;
    
    try {
      await api.delete(`/memory/wiki/${pageData.slug}`);
      alert(`Success: Wiki page "${pageData.title}" deleted.`);
      
      const deletedSlug = pageData.slug;
      setPageData(null);
      setSelectedSlug(null);
      setPages(prev => prev.filter(p => p.slug !== deletedSlug));
    } catch (err) {
      console.error("Failed to delete page", err);
      alert("Failed to delete the page. Please check the backend logs.");
    }
  };

  const filteredPages = pages.filter(p => 
    p.title.toLowerCase().includes(search.toLowerCase()) || 
    p.slug.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="flex h-full min-w-0">
      {/* Page List */}
      <div className="w-80 bg-white border-r border-slate-200 flex flex-col">
        <div className="p-4 border-b border-slate-200">
          <div className="relative">
            <Search size={16} className="absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              placeholder="Search wiki..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-slate-100 border-none rounded-lg pl-10 pr-4 py-2 text-sm focus:ring-2 focus:ring-indigo-500"
            />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {filteredPages.map(p => (
            <button
              key={p.slug}
              onClick={() => setSelectedSlug(p.slug)}
              className={cn(
                "w-full text-left p-3 rounded-xl transition-all group",
                selectedSlug === p.slug ? "bg-indigo-50 border-indigo-100" : "hover:bg-slate-50"
              )}
            >
              <div className="flex items-center justify-between mb-1">
                <span className={cn("text-sm font-semibold", selectedSlug === p.slug ? "text-indigo-700" : "text-slate-700")}>
                  {p.title}
                </span>
                <ChevronRight size={14} className={cn("transition-transform", selectedSlug === p.slug ? "text-indigo-500 translate-x-0" : "text-slate-300 -translate-x-2 opacity-0 group-hover:translate-x-0 group-hover:opacity-100")} />
              </div>
              <div className="flex items-center gap-2">
                <div className="flex-1 h-1 bg-slate-200 rounded-full overflow-hidden">
                  <div 
                    className={cn("h-full rounded-full transition-all duration-500", p.confidence > 0.7 ? "bg-emerald-400" : p.confidence > 0.4 ? "bg-amber-400" : "bg-rose-400")} 
                    style={{ width: `${p.confidence * 100}%` }} 
                  />
                </div>
                <span className="text-[10px] font-medium text-slate-400">{(p.confidence * 100).toFixed(0)}%</span>
              </div>
              <div className="mt-1 flex items-center gap-2">
                <div className="flex-1 h-1 bg-slate-200 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full bg-cyan-400 transition-all duration-500"
                    style={{ width: `${((p.retrievability ?? 1) * 100)}%` }}
                  />
                </div>
                <span className="text-[10px] font-medium text-slate-400">R {((p.retrievability ?? 1) * 100).toFixed(0)}%</span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Page Content */}
      <div className="flex-1 bg-white overflow-y-auto">
        {pageData ? (
          <div className="max-w-4xl mx-auto p-12">
            <header className="mb-12">
              <div className="flex items-center justify-between gap-4 mb-4">
                <div className="flex items-center gap-2 text-xs font-bold text-indigo-600 uppercase tracking-widest">
                  <Book size={14} /> Wiki Page
                </div>
                {isEditing ? (
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setIsEditing(false)}
                      disabled={isSaving}
                      className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-100"
                    >
                      <X size={14} /> Cancel
                    </button>
                    <button
                      onClick={saveEdit}
                      disabled={isSaving}
                      className="inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
                    >
                      <Save size={14} /> {isSaving ? 'Saving' : 'Save'}
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={handleDeletePage}
                      className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold text-rose-400 hover:bg-rose-950/40 hover:text-rose-200 transition-colors cursor-pointer"
                    >
                      <Trash2 size={14} /> Delete
                    </button>
                    <button
                      type="button"
                      onClick={startEdit}
                      className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-100"
                    >
                      <Pencil size={14} /> Edit
                    </button>
                  </div>
                )}
              </div>
              {isEditing ? (
                <div className="space-y-4">
                  <input
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-3xl font-extrabold text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                  <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
                    <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Tags
                      <input
                        value={editTags}
                        onChange={(e) => setEditTags(e.target.value)}
                        className="mt-1 w-full rounded-md border border-slate-200 px-3 py-2 text-sm normal-case tracking-normal text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      />
                    </label>
                    <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Confidence
                      <input
                        type="number"
                        min="0"
                        max="1"
                        step="0.01"
                        value={editConfidence}
                        onChange={(e) => setEditConfidence(e.target.value)}
                        className="mt-1 w-full rounded-md border border-slate-200 px-3 py-2 text-sm normal-case tracking-normal text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      />
                    </label>
                    <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Importance
                      <input
                        type="number"
                        min="0"
                        max="1"
                        step="0.01"
                        value={editImportance}
                        onChange={(e) => setEditImportance(e.target.value)}
                        className="mt-1 w-full rounded-md border border-slate-200 px-3 py-2 text-sm normal-case tracking-normal text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      />
                    </label>
                    <label className="flex items-center gap-2 rounded-md border border-slate-200 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                      <input
                        type="checkbox"
                        checked={editPinned}
                        onChange={(e) => setEditPinned(e.target.checked)}
                        className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                      />
                      Pinned
                    </label>
                  </div>
                </div>
              ) : (
                <h1 className="text-4xl font-extrabold text-slate-900 mb-6 tracking-tight leading-tight">
                  {pageData.title}
                </h1>
              )}
              
              {!isEditing && <div className="flex flex-wrap gap-4 items-center text-sm text-slate-500">
                <div className="flex items-center gap-1.5 bg-slate-100 px-3 py-1.5 rounded-full">
                  <ShieldCheck size={16} className="text-indigo-500" />
                  <span className="font-medium">v{pageData.version}</span>
                </div>
                {pageData.pinned && (
                  <div className="flex items-center gap-1.5 bg-emerald-50 px-3 py-1.5 rounded-full text-emerald-700">
                    <ShieldCheck size={16} />
                    <span className="font-medium">Pinned</span>
                  </div>
                )}
                <div className="flex items-center gap-1.5 bg-slate-100 px-3 py-1.5 rounded-full">
                  <Clock size={16} />
                  <span>Last updated {new Date().toLocaleDateString()}</span>
                </div>
                <div className="flex items-center gap-2">
                  {pageData.tags.map(t => (
                    <span key={t} className="flex items-center gap-1 bg-indigo-50 text-indigo-600 px-2 py-1 rounded text-[11px] font-bold">
                      <Tag size={12} /> {t}
                    </span>
                  ))}
                </div>
              </div>}
            </header>

            {isEditing ? (
              <textarea
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                className="mb-10 min-h-[520px] w-full resize-y rounded-lg border border-slate-200 p-4 font-mono text-sm leading-relaxed text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            ) : (
              <>
                <section className="mb-8 grid grid-cols-2 gap-3 border-y border-slate-100 py-4 md:grid-cols-4">
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Retrievability</div>
                    <div className="mt-1 text-sm font-semibold text-slate-800">{((pageData.retrievability ?? 1) * 100).toFixed(0)}%</div>
                  </div>
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Stability</div>
                    <div className="mt-1 text-sm font-semibold text-slate-800">{(pageData.stability_days ?? 0).toFixed(1)} days</div>
                  </div>
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Difficulty</div>
                    <div className="mt-1 text-sm font-semibold text-slate-800">{((pageData.difficulty ?? 0) * 100).toFixed(0)}%</div>
                  </div>
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Events</div>
                    <div className="mt-1 text-sm font-semibold text-slate-800">
                      {pageData.review_count ?? 0} reviews / {pageData.reinforced_count ?? 0} reinforced
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Last Accessed</div>
                    <div className="mt-1 text-xs font-medium text-slate-600">
                      {pageData.last_accessed ? new Date(pageData.last_accessed).toLocaleString() : 'Never'}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Last Reviewed</div>
                    <div className="mt-1 text-xs font-medium text-slate-600">
                      {pageData.last_reviewed ? new Date(pageData.last_reviewed).toLocaleString() : 'Never'}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Conflicts</div>
                    <div className="mt-1 text-sm font-semibold text-slate-800">{pageData.conflict_count ?? 0}</div>
                  </div>
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Importance</div>
                    <div className="mt-1 text-sm font-semibold text-slate-800">{((pageData.importance ?? 0) * 100).toFixed(0)}%</div>
                  </div>
                </section>
                <div className="prose prose-slate prose-indigo max-w-none mb-10">
                  <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
                    {pageData.content || ''}
                  </ReactMarkdown>
                </div>
                {pageData.source_log_entries && pageData.source_log_entries.length > 0 && (
                  <section className="mb-16 border-t border-slate-100 pt-8">
                    <h3 className="mb-3 text-sm font-bold uppercase tracking-wide text-slate-500">Sources</h3>
                    <div className="flex flex-wrap gap-2">
                      {pageData.source_log_entries.map(entryId => (
                        <span key={entryId} className="rounded bg-slate-100 px-2 py-1 font-mono text-xs text-slate-600">
                          {entryId}
                        </span>
                      ))}
                    </div>
                  </section>
                )}
              </>
            )}

            {!isEditing && pageData.update_log && pageData.update_log.length > 0 && (
              <section className="border-t border-slate-100 pt-12">
                <h3 className="text-lg font-bold text-slate-900 mb-6 flex items-center gap-2">
                  <HistoryIcon size={18} className="text-slate-400" /> Update Log
                </h3>
                <div className="space-y-4">
                  {pageData.update_log.map((log, i) => (
                    <div key={i} className="flex gap-4 group">
                      <div className="flex flex-col items-center">
                        <div className="w-2.5 h-2.5 rounded-full border-2 border-indigo-500 bg-white z-10" />
                        {i !== pageData.update_log!.length - 1 && <div className="w-0.5 flex-1 bg-slate-100 my-1" />}
                      </div>
                      <div className="pb-6">
                        <div className="text-[11px] font-bold text-indigo-500 uppercase tracking-wide mb-1">
                          Version {log.version} • {new Date(log.date).toLocaleString()}
                        </div>
                        <p className="text-sm text-slate-600 leading-relaxed">{log.reason}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>
        ) : (
          <div className="h-full flex items-center justify-center text-slate-400">
            Select a page to view its contents.
          </div>
        )}
      </div>
    </div>
  );
}
