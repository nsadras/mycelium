import { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import { Book, ChevronRight, Clock, History as HistoryIcon, Search, ShieldCheck, Tag } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

import api, { type PageType, type WikiPage } from '../lib/api';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const PAGE_GROUPS: { type: PageType | null; label: string }[] = [
  { type: 'you', label: 'You' },
  { type: 'project', label: 'Projects' },
  { type: 'person', label: 'People' },
  { type: 'topic', label: 'Topics' },
  { type: 'organization', label: 'Organizations' },
  { type: 'place', label: 'Places' },
  { type: 'event', label: 'Events' },
  { type: null, label: 'Unclassified' },
];

function pageTypeLabel(pageType: PageType | null) {
  return PAGE_GROUPS.find((group) => group.type === pageType)?.label ?? 'Unclassified';
}

export default function WikiExplorer() {
  const [pages, setPages] = useState<WikiPage[]>([]);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [pageData, setPageData] = useState<WikiPage | null>(null);
  const [search, setSearch] = useState('');

  useEffect(() => {
    api.get('/memory/wiki')
      .then((response) => setPages(response.data))
      .catch((error) => console.error('Failed to fetch wiki pages', error));
  }, []);

  useEffect(() => {
    if (!selectedSlug) return;
    api.get(`/memory/wiki/${selectedSlug}`)
      .then((response) => setPageData(response.data))
      .catch((error) => console.error('Failed to fetch page', error));
  }, [selectedSlug]);

  const filteredPages = pages.filter((page) => (
    page.title.toLowerCase().includes(search.toLowerCase())
    || page.slug.toLowerCase().includes(search.toLowerCase())
    || pageTypeLabel(page.page_type).toLowerCase().includes(search.toLowerCase())
  ));

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col md:flex-row">
      <div className="flex h-64 w-full shrink-0 flex-col border-b border-slate-200 bg-white md:h-full md:w-80 md:border-b-0 md:border-r">
        <div className="border-b border-slate-200 p-4">
          <div className="relative">
            <Search size={16} className="absolute left-3 top-2.5 text-slate-400" />
            <input type="text" placeholder="Search wiki..." value={search} onChange={(event) => setSearch(event.target.value)} className="w-full rounded-lg border-none bg-slate-100 py-2 pl-10 pr-4 text-sm focus:ring-2 focus:ring-indigo-500" />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {PAGE_GROUPS.map((group) => {
            const groupPages = filteredPages.filter((page) => page.page_type === group.type);
            if (groupPages.length === 0) return null;
            return (
              <section key={group.label} className="mb-4">
                <h2 className="px-3 pb-1 pt-2 text-[10px] font-bold uppercase tracking-widest text-slate-400">{group.label}</h2>
                <div className="space-y-1">
                  {groupPages.sort((left, right) => left.title.localeCompare(right.title)).map((page) => (
                    <button key={page.slug} onClick={() => setSelectedSlug(page.slug)} className={cn('group w-full rounded-xl p-3 text-left transition-all', selectedSlug === page.slug ? 'bg-indigo-50' : 'hover:bg-slate-50')}>
                      <div className="mb-1 flex items-center justify-between">
                        <span className={cn('text-sm font-semibold', selectedSlug === page.slug ? 'text-indigo-700' : 'text-slate-700')}>{page.title}</span>
                        <ChevronRight size={14} className="text-slate-300" />
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="h-1 flex-1 overflow-hidden rounded-full bg-slate-200"><div className={cn('h-full rounded-full', page.confidence > 0.7 ? 'bg-emerald-400' : page.confidence > 0.4 ? 'bg-amber-400' : 'bg-rose-400')} style={{ width: `${page.confidence * 100}%` }} /></div>
                        <span className="text-[10px] font-medium text-slate-400">{(page.confidence * 100).toFixed(0)}%</span>
                      </div>
                    </button>
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto bg-white">
        {pageData ? (
          <div className="mx-auto max-w-4xl p-6 md:p-12">
            <header className="mb-10">
              <div className="mb-4 flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-indigo-600"><Book size={14} /> Generated Wiki View</div>
              <h1 className="mb-6 text-4xl font-extrabold leading-tight tracking-tight text-slate-900">{pageData.title}</h1>
              <div className="flex flex-wrap items-center gap-3 text-sm text-slate-500">
                <span className="flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1.5"><ShieldCheck size={16} className="text-indigo-500" /> v{pageData.version}</span>
                <span className="flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1.5"><Clock size={16} /> Confidence {(pageData.confidence * 100).toFixed(0)}%</span>
                <span className="rounded-full bg-slate-100 px-3 py-1.5">Importance {((pageData.importance ?? 0) * 100).toFixed(0)}%</span>
                <span className="rounded-full bg-indigo-50 px-3 py-1.5 font-semibold text-indigo-600">{pageTypeLabel(pageData.page_type)}</span>
                {pageData.tags.filter((tag) => !tag.startsWith('page-type-')).map((tag) => <span key={tag} className="flex items-center gap-1 rounded bg-indigo-50 px-2 py-1 text-[11px] font-bold text-indigo-600"><Tag size={12} /> {tag}</span>)}
              </div>
            </header>

            <div className="prose prose-slate prose-indigo mb-10 max-w-none">
              <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>{pageData.content || ''}</ReactMarkdown>
            </div>
            {(pageData.source_log_entries?.length ?? 0) > 0 && (
              <section className="mb-12 border-t border-slate-100 pt-8">
                <h3 className="mb-3 text-sm font-bold uppercase tracking-wide text-slate-500">Sources</h3>
                <div className="flex flex-wrap gap-2">{(pageData.source_log_entries ?? []).map((entryId) => <span key={entryId} className="rounded bg-slate-100 px-2 py-1 font-mono text-xs text-slate-600">{entryId}</span>)}</div>
              </section>
            )}
            {(pageData.update_log?.length ?? 0) > 0 && (
              <section className="border-t border-slate-100 pt-10">
                <h3 className="mb-6 flex items-center gap-2 text-lg font-bold text-slate-900"><HistoryIcon size={18} className="text-slate-400" /> Update Log</h3>
                <div className="space-y-4">{(pageData.update_log ?? []).map((log, index) => <div key={`${log.version}-${index}`} className="rounded-lg border border-slate-100 bg-slate-50 p-4"><div className="mb-1 flex items-center justify-between text-xs text-slate-500"><span className="font-semibold">Version {log.version}</span><span>{new Date(log.date).toLocaleString()}</span></div><p className="text-sm text-slate-700">{log.reason}</p></div>)}</div>
              </section>
            )}
          </div>
        ) : (
          <div className="flex h-full flex-col items-center justify-center p-8 text-center text-slate-400"><Book size={42} className="mb-4 opacity-30" /><p className="font-medium">Select a generated wiki page to inspect it.</p></div>
        )}
      </div>
    </div>
  );
}
