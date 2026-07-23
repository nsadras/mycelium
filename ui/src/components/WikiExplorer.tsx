import { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import {
  Book,
  ChevronRight,
  Clock,
  History as HistoryIcon,
  Pencil,
  Save,
  Search,
  ShieldCheck,
  Tag,
  Trash2,
  X,
} from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

import api, { type WikiPage } from '../lib/api';

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
  const [editContent, setEditContent] = useState('');

  useEffect(() => {
    const fetchPages = async () => {
      try {
        const response = await api.get('/memory/wiki');
        setPages(response.data);
      } catch (error) {
        console.error('Failed to fetch wiki pages', error);
      }
    };

    void fetchPages();
  }, []);

  useEffect(() => {
    if (!selectedSlug) return;

    const fetchPage = async () => {
      try {
        const response = await api.get(`/memory/wiki/${selectedSlug}`);
        setPageData(response.data);
        setIsEditing(false);
      } catch (error) {
        console.error('Failed to fetch page', error);
      }
    };

    void fetchPage();
  }, [selectedSlug]);

  const startEdit = () => {
    if (!pageData) return;
    setEditTitle(pageData.title);
    setEditTags(pageData.tags.join(', '));
    setEditConfidence(String(pageData.confidence ?? 0.5));
    setEditImportance(String(pageData.importance ?? 0.5));
    setEditContent(pageData.content || '');
    setIsEditing(true);
  };

  const saveEdit = async () => {
    if (!pageData) return;
    setIsSaving(true);
    try {
      const response = await api.put(`/memory/wiki/${pageData.slug}`, {
        title: editTitle,
        content: editContent,
        tags: editTags.split(',').map((tag) => tag.trim()).filter(Boolean),
        confidence: Number(editConfidence),
        importance: Number(editImportance),
      });
      setPageData(response.data);
      setPages((current) => current.map((page) => (
        page.slug === response.data.slug ? { ...page, ...response.data } : page
      )));
      setIsEditing(false);
    } catch (error) {
      console.error('Failed to save wiki page', error);
      alert('Failed to save wiki page.');
    } finally {
      setIsSaving(false);
    }
  };

  const deletePage = async () => {
    if (!pageData) return;
    const confirmed = window.confirm(
      `Archive the wiki page "${pageData.title}" and remove it from the index?`,
    );
    if (!confirmed) return;

    try {
      await api.delete(`/memory/wiki/${pageData.slug}`);
      const deletedSlug = pageData.slug;
      setPageData(null);
      setSelectedSlug(null);
      setPages((current) => current.filter((page) => page.slug !== deletedSlug));
    } catch (error) {
      console.error('Failed to delete page', error);
      alert('Failed to delete the page.');
    }
  };

  const filteredPages = pages.filter((page) => (
    page.title.toLowerCase().includes(search.toLowerCase())
    || page.slug.toLowerCase().includes(search.toLowerCase())
  ));

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col md:flex-row">
      <div className="flex h-64 w-full shrink-0 flex-col border-b border-slate-200 bg-white md:h-full md:w-80 md:border-b-0 md:border-r">
        <div className="border-b border-slate-200 p-4">
          <div className="relative">
            <Search size={16} className="absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              placeholder="Search wiki..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="w-full rounded-lg border-none bg-slate-100 py-2 pl-10 pr-4 text-sm focus:ring-2 focus:ring-indigo-500"
            />
          </div>
        </div>
        <div className="flex-1 space-y-1 overflow-y-auto p-2">
          {filteredPages.map((page) => (
            <button
              key={page.slug}
              onClick={() => setSelectedSlug(page.slug)}
              className={cn(
                'group w-full rounded-xl p-3 text-left transition-all',
                selectedSlug === page.slug ? 'bg-indigo-50' : 'hover:bg-slate-50',
              )}
            >
              <div className="mb-1 flex items-center justify-between">
                <span className={cn(
                  'text-sm font-semibold',
                  selectedSlug === page.slug ? 'text-indigo-700' : 'text-slate-700',
                )}>
                  {page.title}
                </span>
                <ChevronRight size={14} className="text-slate-300" />
              </div>
              <div className="flex items-center gap-2">
                <div className="h-1 flex-1 overflow-hidden rounded-full bg-slate-200">
                  <div
                    className={cn(
                      'h-full rounded-full',
                      page.confidence > 0.7
                        ? 'bg-emerald-400'
                        : page.confidence > 0.4 ? 'bg-amber-400' : 'bg-rose-400',
                    )}
                    style={{ width: `${page.confidence * 100}%` }}
                  />
                </div>
                <span className="text-[10px] font-medium text-slate-400">
                  {(page.confidence * 100).toFixed(0)}%
                </span>
              </div>
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto bg-white">
        {pageData ? (
          <div className="mx-auto max-w-4xl p-6 md:p-12">
            <header className="mb-10">
              <div className="mb-4 flex items-center justify-between gap-4">
                <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-indigo-600">
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
                      onClick={deletePage}
                      className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold text-rose-500 hover:bg-rose-50"
                    >
                      <Trash2 size={14} /> Delete
                    </button>
                    <button
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
                    onChange={(event) => setEditTitle(event.target.value)}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-3xl font-extrabold text-slate-900 focus:ring-2 focus:ring-indigo-500"
                  />
                  <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                    <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Tags
                      <input
                        value={editTags}
                        onChange={(event) => setEditTags(event.target.value)}
                        className="mt-1 w-full rounded-md border border-slate-200 px-3 py-2 text-sm normal-case tracking-normal text-slate-800"
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
                        onChange={(event) => setEditConfidence(event.target.value)}
                        className="mt-1 w-full rounded-md border border-slate-200 px-3 py-2 text-sm normal-case tracking-normal text-slate-800"
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
                        onChange={(event) => setEditImportance(event.target.value)}
                        className="mt-1 w-full rounded-md border border-slate-200 px-3 py-2 text-sm normal-case tracking-normal text-slate-800"
                      />
                    </label>
                  </div>
                </div>
              ) : (
                <>
                  <h1 className="mb-6 text-4xl font-extrabold leading-tight tracking-tight text-slate-900">
                    {pageData.title}
                  </h1>
                  <div className="flex flex-wrap items-center gap-3 text-sm text-slate-500">
                    <span className="flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1.5">
                      <ShieldCheck size={16} className="text-indigo-500" /> v{pageData.version}
                    </span>
                    <span className="flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1.5">
                      <Clock size={16} /> Confidence {(pageData.confidence * 100).toFixed(0)}%
                    </span>
                    <span className="rounded-full bg-slate-100 px-3 py-1.5">
                      Importance {((pageData.importance ?? 0) * 100).toFixed(0)}%
                    </span>
                    {pageData.tags.map((tag) => (
                      <span key={tag} className="flex items-center gap-1 rounded bg-indigo-50 px-2 py-1 text-[11px] font-bold text-indigo-600">
                        <Tag size={12} /> {tag}
                      </span>
                    ))}
                  </div>
                </>
              )}
            </header>

            {isEditing ? (
              <textarea
                value={editContent}
                onChange={(event) => setEditContent(event.target.value)}
                className="mb-10 min-h-[520px] w-full resize-y rounded-lg border border-slate-200 p-4 font-mono text-sm leading-relaxed text-slate-800 focus:ring-2 focus:ring-indigo-500"
              />
            ) : (
              <>
                <div className="prose prose-slate prose-indigo mb-10 max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
                    {pageData.content || ''}
                  </ReactMarkdown>
                </div>
                {pageData.source_log_entries && pageData.source_log_entries.length > 0 && (
                  <section className="mb-12 border-t border-slate-100 pt-8">
                    <h3 className="mb-3 text-sm font-bold uppercase tracking-wide text-slate-500">Sources</h3>
                    <div className="flex flex-wrap gap-2">
                      {pageData.source_log_entries.map((entryId) => (
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
              <section className="border-t border-slate-100 pt-10">
                <h3 className="mb-6 flex items-center gap-2 text-lg font-bold text-slate-900">
                  <HistoryIcon size={18} className="text-slate-400" /> Update Log
                </h3>
                <div className="space-y-4">
                  {pageData.update_log.map((log, index) => (
                    <div key={`${log.version}-${index}`} className="rounded-lg border border-slate-100 bg-slate-50 p-4">
                      <div className="mb-1 flex items-center justify-between text-xs text-slate-500">
                        <span className="font-semibold">Version {log.version}</span>
                        <span>{new Date(log.date).toLocaleString()}</span>
                      </div>
                      <p className="text-sm text-slate-700">{log.reason}</p>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>
        ) : (
          <div className="flex h-full flex-col items-center justify-center p-8 text-center text-slate-400">
            <Book size={42} className="mb-4 opacity-30" />
            <p className="font-medium">Select a wiki page to inspect it.</p>
          </div>
        )}
      </div>
    </div>
  );
}
