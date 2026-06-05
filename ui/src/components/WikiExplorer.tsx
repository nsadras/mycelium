import { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import { Search, Tag, Clock, ShieldCheck, ChevronRight, Book, History as HistoryIcon, Pencil, Save, X, Trash2, Brain, TrendingDown, Sparkles, Zap, Info } from 'lucide-react';
import api, { type WikiPage } from '../lib/api';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const calculateDecayPoints = (page: WikiPage) => {
  const isPinned = !!page.pinned;
  const S = page.stability_days ?? 30.0;
  const maxDays = Math.max(60, Math.min(180, S * 3));

  // Viewport coordinates
  const xMin = 45;
  const xMax = 460;
  const yMin = 15;
  const yMax = 135;

  const mapX = (t: number) => xMin + (t / maxDays) * (xMax - xMin);
  const mapY = (r: number) => yMax - r * (yMax - yMin);

  // Compute elapsed time
  const now = new Date();
  const createdStr = (page as any).created || page.last_reviewed || null;
  const anchor = page.last_reviewed ? new Date(page.last_reviewed) : (createdStr ? new Date(createdStr) : now);
  const elapsedDays = Math.max(0, (now.getTime() - anchor.getTime()) / (1000 * 60 * 60 * 24));

  // Current point
  const currentR = isPinned ? 1.0 : (page.retrievability ?? 1.0);
  const currentX = mapX(Math.min(maxDays, elapsedDays));
  const currentY = mapY(currentR);

  // Calculate stability multipliers (review & contradiction)
  const diff = page.difficulty ?? 0.25;
  const imp = page.importance ?? 0.5;
  const difficultyFactor = 1.0 - Math.max(0, Math.min(1, diff));
  const importanceFactor = 0.5 + Math.max(0, Math.min(1, imp));

  const reviewMultiplier = 1.10 + (0.20 * importanceFactor * (0.5 + difficultyFactor));
  const s2 = Math.max(1.0, Math.min(3650.0, S * reviewMultiplier));
  const s3 = Math.max(1.0, Math.min(3650.0, S * 0.85));

  // Generate paths by sampling 30 points
  const samplePoints = 30;
  let baseD = '';
  let reviewD = '';
  let conflictD = '';

  if (isPinned) {
    baseD = `M ${xMin} ${yMin} L ${xMax} ${yMin}`;
  } else {
    const basePoints: string[] = [];
    const reviewPoints: string[] = [];
    const conflictPoints: string[] = [];

    for (let i = 0; i <= samplePoints; i++) {
      const t = (i / samplePoints) * maxDays;
      const x = mapX(t);

      // 1. Natural Decay
      const rBase = Math.exp(-t / S);
      basePoints.push(`${x.toFixed(1)},${mapY(rBase).toFixed(1)}`);

      // 2. Reinforced (starts at R=1.0, decays with s2)
      const rReview = Math.exp(-t / s2);
      reviewPoints.push(`${x.toFixed(1)},${mapY(rReview).toFixed(1)}`);

      // 3. Contradicted (starts at R=0.85, decays with s3)
      const rConflict = 0.85 * Math.exp(-t / s3);
      conflictPoints.push(`${x.toFixed(1)},${mapY(rConflict).toFixed(1)}`);
    }

    baseD = `M ` + basePoints.join(' L ');
    reviewD = `M ` + reviewPoints.join(' L ');
    conflictD = `M ` + conflictPoints.join(' L ');
  }

  return {
    isPinned,
    maxDays,
    currentX,
    currentY,
    currentR,
    elapsedDays,
    sBase: S,
    s2,
    s3,
    reviewMultiplier,
    baseD,
    reviewD,
    conflictD,
  };
};

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
  const [showDecayDashboard, setShowDecayDashboard] = useState(false);

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
      setShowDecayDashboard(false);
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

  const decayData = pageData ? calculateDecayPoints(pageData) : null;

  return (
    <div className="flex flex-col md:flex-row flex-1 min-h-0 min-w-0">
      {/* Page List */}
      <div className="w-full md:w-80 h-64 md:h-full bg-white border-b md:border-b-0 md:border-r border-slate-200 flex flex-col shrink-0">
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

                {/* Minimalist Toggle Bar */}
                {decayData && !showDecayDashboard && (
                  <button
                    onClick={() => setShowDecayDashboard(true)}
                    className="w-full mb-8 bg-slate-900/50 hover:bg-slate-900 border border-slate-800/80 rounded-xl px-5 py-3 flex items-center justify-between text-slate-300 hover:text-white transition-all group cursor-pointer shadow-md"
                  >
                    <div className="flex items-center gap-2.5">
                      <Brain className="text-teal-400 w-4 h-4 group-hover:animate-pulse" />
                      <span className="text-xs font-semibold tracking-wide">
                        View Memory Decay Curve
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-[10px] text-slate-500 group-hover:text-slate-400">
                      <span>R = {(decayData.currentR * 100).toFixed(0)}% • S = {decayData.sBase.toFixed(1)}d</span>
                      <ChevronRight size={14} className="transform group-hover:translate-x-0.5 transition-transform" />
                    </div>
                  </button>
                )}

                {/* Cognitive Memory Analytics Dashboard */}
                {decayData && showDecayDashboard && (
                  <section className="mb-10 bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl text-slate-100">
                    <div 
                      onClick={() => setShowDecayDashboard(false)}
                      className="flex items-center justify-between mb-6 pb-4 border-b border-slate-800 cursor-pointer group"
                    >
                      <div className="flex items-center gap-2">
                        <Brain className="text-teal-400 w-5 h-5 group-hover:scale-105 transition-transform" />
                        <div>
                          <h2 className="text-base font-bold text-slate-100 tracking-tight">
                            Cognitive Memory Analytics
                          </h2>
                          <p className="text-[11px] text-slate-400">
                            Natural forgetting curve projection vs. reinforced review pathways (Click header to collapse)
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-4 text-xs">
                        {decayData.isPinned ? (
                          <span className="flex items-center gap-1.5 bg-emerald-950/60 text-emerald-400 px-3 py-1 rounded-full border border-emerald-900/50 font-semibold">
                            <Sparkles size={12} /> Pinned Immortal Memory
                          </span>
                        ) : (
                          <span className="text-slate-400">
                            Half-life stability: <strong className="text-slate-200">{decayData.sBase.toFixed(1)}d</strong>
                          </span>
                        )}
                        <ChevronRight size={14} className="transform rotate-90 text-slate-500 group-hover:translate-y-0.5 group-hover:text-slate-300 transition-transform" />
                      </div>
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
                      {/* SVG Plot Column (7 cols) */}
                      <div className="lg:col-span-7 bg-slate-950/50 border border-slate-950 rounded-xl p-4 relative overflow-hidden">
                        {/* Title of the chart */}
                        <div className="flex items-center justify-between mb-3 text-[11px] text-slate-400 px-1">
                          <span className="font-semibold flex items-center gap-1"><TrendingDown size={12} /> Retrievability (R) vs Time (t)</span>
                          <span className="font-mono bg-slate-900 px-2 py-0.5 rounded text-[10px] text-slate-500">Plot range: 0 to {decayData.maxDays} days</span>
                        </div>

                        {/* Interactive Pure SVG Chart */}
                        <svg viewBox="0 0 480 160" className="w-full h-auto overflow-visible select-none">
                          {/* Grid Lines & Labels */}
                          {[0, 0.25, 0.5, 0.75, 1.0].map((r) => {
                            const y = 135 - r * 120;
                            return (
                              <g key={r} className="opacity-45">
                                <line
                                  x1="45"
                                  y1={y}
                                  x2="460"
                                  y2={y}
                                  className="stroke-slate-800"
                                  strokeWidth="1"
                                  strokeDasharray={r === 0 ? "0" : "2 2"}
                                />
                                <text
                                  x="35"
                                  y={y + 3}
                                  className="fill-slate-500 text-[10px] font-mono text-right font-bold"
                                  textAnchor="end"
                                >
                                  {Math.round(r * 100)}%
                                </text>
                              </g>
                            );
                          })}

                          {/* Time Ticks */}
                          {[0, 0.25, 0.5, 0.75, 1.0].map((ratio) => {
                            const t = ratio * decayData.maxDays;
                            const x = 45 + ratio * 415;
                            return (
                              <g key={ratio} className="opacity-45">
                                <line
                                  x1={x}
                                  y1="15"
                                  x2={x}
                                  y2="135"
                                  className="stroke-slate-800"
                                  strokeWidth="1"
                                  strokeDasharray="2 2"
                                />
                                <text
                                  x={x}
                                  y="148"
                                  className="fill-slate-500 text-[10px] font-mono font-bold"
                                  textAnchor="middle"
                                >
                                  {Math.round(t)}d
                                </text>
                              </g>
                            );
                          })}

                          {/* Render Curve Paths */}
                          {!decayData.isPinned ? (
                            <>
                              {/* 1. Reinforced review path (emerald green dashed) */}
                              <path
                                d={decayData.reviewD}
                                fill="none"
                                className="stroke-emerald-500/60"
                                strokeWidth="2"
                                strokeDasharray="5 3"
                              />

                              {/* 2. Contradicted path (rose dashed) */}
                              <path
                                d={decayData.conflictD}
                                fill="none"
                                className="stroke-rose-500/50"
                                strokeWidth="1.5"
                                strokeDasharray="3 3"
                              />

                              {/* 3. Base natural decay path (teal solid glow + main) */}
                              <path
                                d={decayData.baseD}
                                fill="none"
                                className="stroke-teal-500/20"
                                strokeWidth="5"
                              />
                              <path
                                d={decayData.baseD}
                                fill="none"
                                className="stroke-teal-400"
                                strokeWidth="2"
                              />
                            </>
                          ) : (
                            <>
                              {/* Pinned flat line (glowing solid green) */}
                              <path
                                d={decayData.baseD}
                                fill="none"
                                className="stroke-emerald-400/20"
                                strokeWidth="6"
                              />
                              <path
                                d={decayData.baseD}
                                fill="none"
                                className="stroke-emerald-400"
                                strokeWidth="2.5"
                              />
                            </>
                          )}

                          {/* Pulsing Recall Dot & Outer Ring */}
                          <g>
                            <circle
                              cx={decayData.currentX}
                              cy={decayData.currentY}
                              r="8"
                              className={decayData.isPinned ? "fill-emerald-400/30" : "fill-teal-400/30"}
                            >
                              <animate attributeName="r" values="5;10;5" dur="2.4s" repeatCount="indefinite" />
                              <animate attributeName="opacity" values="0.9;0.1;0.9" dur="2.4s" repeatCount="indefinite" />
                            </circle>
                            <circle
                              cx={decayData.currentX}
                              cy={decayData.currentY}
                              r="4.5"
                              className={decayData.isPinned ? "fill-emerald-400 stroke-slate-950" : "fill-teal-400 stroke-slate-950"}
                              strokeWidth="1.5"
                            />
                          </g>
                        </svg>

                        {/* Custom Map Legend overlayed below chart */}
                        <div className="flex flex-wrap gap-x-4 gap-y-1.5 mt-4 pt-3 border-t border-slate-900/60 text-[10px] font-medium justify-center text-slate-400">
                          {decayData.isPinned ? (
                            <div className="flex items-center gap-1.5">
                              <span className="w-3 h-0.5 bg-emerald-400 inline-block" />
                              <span className="text-emerald-400">Immortal Memory (100% Locked)</span>
                            </div>
                          ) : (
                            <>
                              <div className="flex items-center gap-1.5">
                                <span className="w-3 h-0.5 bg-teal-400 inline-block" />
                                <span>Natural Decay Curve</span>
                              </div>
                              <div className="flex items-center gap-1.5">
                                <span className="w-3 h-0.5 border-t-2 border-dashed border-emerald-500 inline-block" />
                                <span className="text-emerald-400">Simulated Review Path (S → {decayData.s2.toFixed(1)}d)</span>
                              </div>
                              <div className="flex items-center gap-1.5">
                                <span className="w-3 h-0.5 border-t-2 border-dashed border-rose-500 inline-block" />
                                <span className="text-rose-400">Simulated Conflict Path (S → {decayData.s3.toFixed(1)}d)</span>
                              </div>
                            </>
                          )}
                        </div>
                      </div>

                      {/* Right Projections Panel (5 cols) */}
                      <div className="lg:col-span-5 flex flex-col gap-3">
                        <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 flex items-center gap-1">
                          <Info size={13} /> Cognitive Forecast
                        </div>

                        {/* Card 1: Recall Strength */}
                        <div className="bg-slate-950/40 border border-slate-900/80 rounded-xl p-3.5 flex items-center justify-between">
                          <div>
                            <span className="text-[10px] text-slate-500 font-bold uppercase block tracking-wider">Recall Strength</span>
                            <span className="text-xs text-slate-300 font-medium">
                              Estimated R = <strong className="text-slate-100 font-mono">{(decayData.currentR * 100).toFixed(0)}%</strong>
                            </span>
                          </div>
                          <div>
                            {decayData.isPinned ? (
                              <span className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2.5 py-1 rounded text-[10px] font-bold uppercase tracking-wider">
                                Immortal
                              </span>
                            ) : decayData.currentR > 0.8 ? (
                              <span className="bg-teal-500/10 text-teal-400 border border-teal-500/20 px-2.5 py-1 rounded text-[10px] font-bold uppercase tracking-wider">
                                Excellent
                              </span>
                            ) : decayData.currentR > 0.5 ? (
                              <span className="bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 px-2.5 py-1 rounded text-[10px] font-bold uppercase tracking-wider">
                                Good
                              </span>
                            ) : decayData.currentR > 0.15 ? (
                              <span className="bg-amber-500/10 text-amber-400 border border-amber-500/20 px-2.5 py-1 rounded text-[10px] font-bold uppercase tracking-wider">
                                Fading
                              </span>
                            ) : (
                              <span className="bg-rose-500/10 text-rose-400 border border-rose-500/20 px-2.5 py-1 rounded text-[10px] font-bold uppercase tracking-wider">
                                Archivable
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Card 2: Active Review Boost */}
                        <div className="bg-slate-950/40 border border-slate-900/80 rounded-xl p-3.5">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Active Review Boost</span>
                            <span className="text-[10px] font-bold text-emerald-400 flex items-center gap-0.5">
                              <Zap size={10} /> +{((decayData.reviewMultiplier - 1) * 100).toFixed(0)}% boost
                            </span>
                          </div>
                          <div className="text-sm font-bold text-slate-200">
                            {decayData.isPinned ? "N/A (Memory Pinned)" : `+${(decayData.s2 - decayData.sBase).toFixed(1)} days stability`}
                          </div>
                          <p className="text-[10px] text-slate-400 mt-1 leading-normal">
                            {decayData.isPinned 
                              ? "Pinned memories do not decay and bypass reinforcement calculations."
                              : `Next active review boosts stability from ${decayData.sBase.toFixed(1)}d to ${decayData.s2.toFixed(1)}d.`
                            }
                          </p>
                        </div>

                        {/* Card 3: Contradiction Penalty */}
                        <div className="bg-slate-950/40 border border-slate-900/80 rounded-xl p-3.5">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Contradiction Risk</span>
                            <span className="text-[10px] font-bold text-rose-400">-15% recall drop</span>
                          </div>
                          <div className="text-sm font-bold text-slate-200">
                            {decayData.isPinned ? "N/A (Protected)" : `-${(decayData.sBase - decayData.s3).toFixed(1)} days stability`}
                          </div>
                          <p className="text-[10px] text-slate-400 mt-1 leading-normal">
                            {decayData.isPinned 
                              ? "Pinned user profile is fully protected from logic contradictions."
                              : `A contradictory event instantly drops recall by 15% and damages stability to ${decayData.s3.toFixed(1)}d.`
                            }
                          </p>
                        </div>

                        {/* Card 4: Archive Eligibility / Memory Status */}
                        <div className="bg-slate-950/40 border border-slate-900/80 rounded-xl p-3.5 text-[10px] text-slate-400 leading-relaxed">
                          <strong className="text-slate-300 font-bold uppercase block mb-1 tracking-wide">Archiving Status</strong>
                          {decayData.isPinned ? (
                            <span className="text-emerald-400 font-medium">Immortal (Pinned page)</span>
                          ) : (pageData.importance ?? 0.0) >= 0.4 || (pageData.confidence ?? 0.0) >= 0.6 ? (
                            <span className="text-teal-400 font-medium">
                              Protected Memory (Imp: {((pageData.importance ?? 0)*100).toFixed(0)}% / Conf: {((pageData.confidence ?? 0)*100).toFixed(0)}%)
                            </span>
                          ) : (
                            <span>
                              Decays below 15% threshold in{" "}
                              <strong className="text-amber-400">
                                {Math.max(0, Math.round(Math.max(30, 1.897 * decayData.sBase) - decayData.elapsedDays))} days
                              </strong>
                              .
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  </section>
                )}

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
