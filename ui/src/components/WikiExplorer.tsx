import { useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Archive, Book, ChevronRight, GitMerge, Pencil, RotateCcw, Search, ShieldCheck, Split, X } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

import api, {
  type EntityRecord,
  type ArtifactSource,
  type MemoryOntology,
  type OrganizationProposalArtifact,
  type PageType,
  type WikiFactItem,
  type WikiPage,
} from '../lib/api';

function cn(...inputs: ClassValue[]) { return twMerge(clsx(inputs)); }

export default function WikiExplorer() {
  const [pages, setPages] = useState<WikiPage[]>([]);
  const [entities, setEntities] = useState<EntityRecord[]>([]);
  const [proposals, setProposals] = useState<OrganizationProposalArtifact[]>([]);
  const [ontology, setOntology] = useState<MemoryOntology | null>(null);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [pageData, setPageData] = useState<WikiPage | null>(null);
  const [search, setSearch] = useState('');
  const [showReview, setShowReview] = useState(false);
  const [editing, setEditing] = useState(false);
  const [expandedClaim, setExpandedClaim] = useState<string | null>(null);
  const [selectedClaims, setSelectedClaims] = useState<string[]>([]);
  const [selectedFacts, setSelectedFacts] = useState<string[]>([]);
  const [groupText, setGroupText] = useState('');

  const refresh = async () => {
    const [pageResponse, entityResponse, proposalResponse, ontologyResponse] = await Promise.all([
      api.get<WikiPage[]>('/memory/wiki'),
      api.get<EntityRecord[]>('/memory/artifacts/entities'),
      api.get<OrganizationProposalArtifact[]>('/memory/artifacts/organization-proposals?status=pending'),
      api.get<MemoryOntology>('/memory/ontology'),
    ]);
    setPages(pageResponse.data);
    setEntities(entityResponse.data);
    setProposals(proposalResponse.data);
    setOntology(ontologyResponse.data);
  };

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.get<WikiPage[]>('/memory/wiki'),
      api.get<EntityRecord[]>('/memory/artifacts/entities'),
      api.get<OrganizationProposalArtifact[]>('/memory/artifacts/organization-proposals?status=pending'),
      api.get<MemoryOntology>('/memory/ontology'),
    ]).then(([pageResponse, entityResponse, proposalResponse, ontologyResponse]) => {
      if (cancelled) return;
      setPages(pageResponse.data);
      setEntities(entityResponse.data);
      setProposals(proposalResponse.data);
      setOntology(ontologyResponse.data);
    }).catch((error) => console.error('Failed to load wiki', error));
    return () => { cancelled = true; };
  }, []);
  useEffect(() => {
    if (!selectedSlug) return;
    api.get<WikiPage>(`/memory/wiki/${encodeURIComponent(selectedSlug)}`)
      .then((response) => setPageData(response.data))
      .catch((error) => console.error('Failed to fetch page', error));
  }, [selectedSlug]);

  const selectedEntity = entities.find((entity) => entity.entity_id === pageData?.entity_id) ?? null;
  const entityTypes = ontology?.entity_types ?? [];
  const pageTypeLabel = (pageType: PageType) => entityTypes.find(
    (definition) => definition.key === pageType
  )?.label ?? pageType;
  const filteredPages = pages.filter((page) => [page.title, page.slug, ...page.aliases]
    .some((value) => value.toLowerCase().includes(search.toLowerCase())));
  const archivedEntities = entities.filter((entity) => entity.status === 'archived'
    && [entity.title, entity.slug, ...entity.aliases]
      .some((value) => value.toLowerCase().includes(search.toLowerCase())));
  const allFactIds = useMemo(() => (pageData?.sections ?? []).flatMap((section) => section.items)
    .filter((item): item is WikiFactItem => item.kind === 'fact')
    .flatMap((item) => item.claim_ids), [pageData]);

  const reloadSelected = async (slug = selectedSlug) => {
    await refresh();
    if (slug) {
      const response = await api.get<WikiPage>(`/memory/wiki/${encodeURIComponent(slug)}`);
      setPageData(response.data);
      setSelectedSlug(response.data.slug);
    } else {
      setPageData(null);
      setSelectedSlug(null);
    }
  };

  const reviewProposal = async (proposalId: string, decision: 'approve' | 'reject') => {
    await api.post(`/memory/organization/proposals/${proposalId}/${decision}`, {});
    await reloadSelected();
  };
  const reactivate = async (entityId: string) => {
    const response = await api.post(`/memory/entities/${entityId}/reactivate`);
    await refresh();
    setSelectedSlug(response.data.entity.slug);
  };
  const groupFacts = async () => {
    if (selectedFacts.length < 2 || !groupText.trim()) return;
    await api.post('/memory/facts/group', { fact_ids: selectedFacts, text: groupText, reason: 'Manual wiki fact grouping' });
    setSelectedFacts([]); setGroupText(''); await reloadSelected();
  };

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col md:flex-row">
      <aside className="flex h-72 w-full shrink-0 flex-col border-b border-slate-200 bg-white md:h-full md:w-80 md:border-b-0 md:border-r">
        <div className="border-b border-slate-200 p-4">
          <div className="relative"><Search size={16} className="absolute left-3 top-2.5 text-slate-400" /><input type="text" placeholder="Search titles and aliases…" value={search} onChange={(event) => setSearch(event.target.value)} className="w-full rounded-lg border-none bg-slate-100 py-2 pl-10 pr-4 text-sm focus:ring-2 focus:ring-indigo-500" /></div>
          <button onClick={() => setShowReview(!showReview)} className={cn('mt-3 w-full rounded-lg px-3 py-2 text-left text-xs font-semibold', showReview ? 'bg-amber-100 text-amber-800' : 'bg-slate-50 text-slate-600')}>Organization review · {proposals.length}</button>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {showReview ? <ReviewQueue proposals={proposals} entities={entities} onReview={reviewProposal} /> : entityTypes.map((group) => {
            const groupPages = filteredPages.filter((page) => page.page_type === group.key);
            if (!groupPages.length) return null;
            return <section key={group.key} className="mb-4"><h2 className="px-3 pb-1 pt-2 text-[10px] font-bold uppercase tracking-widest text-slate-400">{group.plural_label}</h2><div className="space-y-1">{groupPages.sort((a, b) => a.title.localeCompare(b.title)).map((page) => <button key={page.entity_id} onClick={() => { setSelectedSlug(page.slug); setShowReview(false); }} className={cn('group w-full rounded-xl p-3 text-left', selectedSlug === page.slug ? 'bg-indigo-50' : 'hover:bg-slate-50')}><div className="flex items-center justify-between"><span className={cn('text-sm font-semibold', selectedSlug === page.slug ? 'text-indigo-700' : 'text-slate-700')}>{page.title}</span><ChevronRight size={14} className="text-slate-300" /></div><div className="mt-1 truncate text-[11px] text-slate-400">{page.slug}</div></button>)}</div></section>;
          })}{!showReview && archivedEntities.length > 0 && <section className="mb-4 border-t border-slate-100 pt-2"><h2 className="px-3 pb-1 pt-2 text-[10px] font-bold uppercase tracking-widest text-slate-400">Archived</h2><div className="space-y-1">{archivedEntities.sort((a, b) => a.title.localeCompare(b.title)).map((entity) => <div key={entity.entity_id} className="flex items-center gap-2 rounded-xl p-3 hover:bg-slate-50"><div className="min-w-0 flex-1"><div className="truncate text-sm font-semibold text-slate-500">{entity.title}</div><div className="truncate text-[11px] text-slate-400">{pageTypeLabel(entity.entity_type)}</div></div><button title="Reactivate entity" onClick={() => reactivate(entity.entity_id)} className="rounded-lg bg-slate-100 p-2 text-slate-500 hover:bg-indigo-50 hover:text-indigo-700"><RotateCcw size={14} /></button></div>)}</div></section>}
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto bg-white">
        {pageData ? <div className="mx-auto max-w-4xl p-6 md:p-12">
          <header className="mb-8">
            <div className="mb-4 flex items-center justify-between"><div className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-indigo-600"><Book size={14} /> Entity-owned wiki</div><button onClick={() => setEditing(!editing)} className="flex items-center gap-2 rounded-lg bg-slate-100 px-3 py-2 text-xs font-semibold text-slate-700"><Pencil size={14} /> Curate</button></div>
            <h1 className="mb-4 text-4xl font-extrabold tracking-tight text-slate-900">{pageData.title}</h1>
            <div className="flex flex-wrap gap-2 text-xs"><span className="rounded-full bg-indigo-50 px-3 py-1.5 font-semibold text-indigo-700">{pageTypeLabel(pageData.page_type as PageType)}</span><span className="rounded-full bg-slate-100 px-3 py-1.5 text-slate-600"><ShieldCheck size={13} className="mr-1 inline" />v{pageData.version}</span><span className="rounded-full bg-slate-100 px-3 py-1.5 font-mono text-slate-500">{pageData.entity_id}</span>{pageData.aliases.map((alias) => <span key={alias} className="rounded-full bg-slate-50 px-3 py-1.5 text-slate-500">alias: {alias}</span>)}</div>
          </header>

          {editing && selectedEntity && ontology && <CurationPanel entity={selectedEntity} entities={entities} ontology={ontology} claimIds={allFactIds} onDone={reloadSelected} onClose={() => setEditing(false)} selectedClaims={selectedClaims} setSelectedClaims={setSelectedClaims} />}

          {selectedFacts.length >= 2 && <div className="mb-6 flex gap-2 rounded-xl border border-indigo-100 bg-indigo-50 p-3"><input value={groupText} onChange={(event) => setGroupText(event.target.value)} placeholder="Combined fact text" className="min-w-0 flex-1 rounded border-slate-200 text-sm" /><button onClick={groupFacts} className="rounded bg-indigo-600 px-3 py-2 text-xs font-semibold text-white">Group {selectedFacts.length} facts</button></div>}
          {(pageData.sections?.length ?? 0) > 0 ? <div className="space-y-10">{pageData.sections!.map((section) => <section key={section.key}><h2 className="mb-4 border-b border-slate-100 pb-2 text-xl font-bold text-slate-900">{section.title}</h2><div className="space-y-3">{section.items.map((item, index) => item.kind === 'link' ? <button key={`${item.entity_id}-${index}`} onClick={() => setSelectedSlug(item.slug)} className="block text-left text-sm font-semibold text-indigo-700 hover:underline">{item.title} <span className="font-normal text-slate-400">· {pageTypeLabel(item.entity_type)}</span></button> : item.kind === 'encounter' ? <div key={item.encounter_id} className="rounded-xl bg-slate-50 p-3 text-sm text-slate-600">{item.text}<div className="mt-1 font-mono text-[10px] text-slate-400">{item.source_id}</div></div> : <div key={item.fact_id} className={cn('rounded-xl border p-4', item.authoritative ? 'border-slate-100 bg-white' : 'border-amber-200 bg-amber-50')}><div className="flex gap-3"><input aria-label="Select fact" type="checkbox" checked={selectedFacts.includes(item.fact_id)} onChange={(event) => { setSelectedFacts((current) => event.target.checked ? [...new Set([...current, item.fact_id])] : current.filter((id) => id !== item.fact_id)); setSelectedClaims((current) => event.target.checked ? [...new Set([...current, ...item.claim_ids])] : current.filter((id) => !item.claim_ids.includes(id))); }} /><button className="flex-1 text-left" onClick={() => setExpandedClaim(expandedClaim === item.fact_id ? null : item.fact_id)}><p className="text-sm leading-relaxed text-slate-800">{item.text}</p><div className="mt-2 flex flex-wrap gap-1"><span className="rounded bg-indigo-50 px-2 py-1 text-[10px] text-indigo-600">{item.synthesis_origin}</span>{item.evidence_modality === 'tool' && <span className="rounded bg-sky-50 px-2 py-1 text-[10px] font-bold uppercase text-sky-700">External research</span>}{item.qualifiers.map((qualifier) => <span key={qualifier} className="rounded bg-slate-100 px-2 py-1 text-[10px] text-slate-500">{qualifier}</span>)}</div></button></div>{expandedClaim === item.fact_id && ontology && <FactEvidence item={item} entities={entities} ontology={ontology} currentEntityId={pageData.entity_id} onMoved={reloadSelected} />}</div>)}</div></section>)}</div> : <div className="prose prose-slate max-w-none"><ReactMarkdown remarkPlugins={[remarkGfm]}>{pageData.content || ''}</ReactMarkdown></div>}
        </div> : <div className="flex h-full flex-col items-center justify-center p-8 text-center text-slate-400"><Book size={42} className="mb-4 opacity-30" /><p>Select a wiki entity to inspect it.</p></div>}
      </main>
    </div>
  );
}

function FactEvidence({ item, entities, ontology, currentEntityId, onMoved }: { item: WikiFactItem; entities: EntityRecord[]; ontology: MemoryOntology; currentEntityId: string; onMoved: (slug?: string | null) => Promise<void> }) {
  const canonicalOwnerId = item.canonical_owner_entity_ids[0] ?? currentEntityId;
  const [owner, setOwner] = useState(canonicalOwnerId);
  const ownerEntity = entities.find((entity) => entity.entity_id === owner);
  const definition = (entity?: EntityRecord) => ontology.entity_types.find((value) => value.key === entity?.entity_type);
  const roleSection = (entity?: EntityRecord) => definition(entity)?.project_role_section ?? '';
  const sections = (entity?: EntityRecord) => definition(entity)?.sections.map((value) => value.key) ?? [];
  const initialSection = item.relationship_kind === 'project_role' ? roleSection(ownerEntity) : sections(ownerEntity)[0] ?? '';
  const [section, setSection] = useState(initialSection);
  const [factText, setFactText] = useState(item.text);
  const [sourceArtifacts, setSourceArtifacts] = useState<Record<string, ArtifactSource>>({});
  const [scopeDecisions, setScopeDecisions] = useState<{ decision_id: string; claim_id: string; origin: 'automatic' | 'manual' | 'review'; confidence: number; reason: string }[]>([]);
  useEffect(() => {
    Promise.all([...new Set(item.sources.map((source) => source.source_id))].map(async (sourceId) => {
      const response = await api.get<ArtifactSource>(`/memory/artifacts/sources/${encodeURIComponent(sourceId)}`);
      return [sourceId, response.data] as const;
    })).then((values) => setSourceArtifacts(Object.fromEntries(values))).catch((error) => console.error('Failed to load source evidence', error));
  }, [item]);
  useEffect(() => {
    Promise.all(item.claim_ids.map(async (claimId) => (await api.get(`/memory/artifacts/scope-decisions?claim_id=${encodeURIComponent(claimId)}&status=active`)).data))
      .then((values) => setScopeDecisions(values.flat()))
      .catch((error) => console.error('Failed to load scope audit', error));
  }, [item]);
  const changeOwner = (value: string) => { setOwner(value); const selected = entities.find((entity) => entity.entity_id === value); setSection(item.relationship_kind === 'project_role' ? roleSection(selected) : sections(selected)[0] ?? ''); };
  const move = async () => { const target = entities.find((entity) => entity.entity_id === owner); await api.post(`/memory/facts/${item.fact_id}/move`, { owner_entity_id: owner, section_key: section, linked_entity_ids: item.canonical_linked_entity_ids, reason: 'Manual wiki fact organization' }); await onMoved(target?.slug); };
  const saveText = async () => { await api.patch(`/memory/facts/${item.fact_id}`, { text: factText, reason: 'Manual wiki fact correction' }); await onMoved(); };
  const split = async () => { const claims = await Promise.all(item.claim_ids.map(async (claimId) => (await api.get<{ claim_id: string; text: string }>(`/memory/artifacts/claims/${encodeURIComponent(claimId)}`)).data)); await api.post(`/memory/facts/${item.fact_id}/split`, { groups: claims.map((claim) => ({ claim_ids: [claim.claim_id], text: claim.text })), reason: 'Manual wiki fact split' }); await onMoved(); };
  const ownerChoices = entities.filter((entity) => entity.status === 'active' && (item.relationship_kind !== 'project_role' || entity.entity_type === 'you' || entity.entity_type === 'person'));
  const sectionChoices = item.relationship_kind === 'project_role' ? [roleSection(ownerEntity)].filter(Boolean) : sections(ownerEntity);
  return <div className="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-500">{item.relationship_kind === 'project_role' && <div className="mb-3 rounded bg-indigo-50 px-2 py-1 text-indigo-700">Shared role view · one canonical relationship shown on both endpoint pages</div>}<div className="mb-2 font-semibold text-slate-700">Consolidated fact</div><div className="flex gap-2"><input value={factText} onChange={(event) => setFactText(event.target.value)} className="min-w-0 flex-1 rounded border-slate-200 text-xs" /><button onClick={saveText} className="rounded bg-slate-800 px-3 py-2 font-semibold text-white">Save text</button>{item.claim_ids.length > 1 && <button onClick={split} className="rounded bg-white px-3 py-2 font-semibold text-slate-600 ring-1 ring-slate-200">Split claims</button>}</div><div className="mt-2 text-[11px]">{item.synthesis_reason} · confidence {item.synthesis_confidence.toFixed(2)}</div><div className="mb-2 mt-3 font-semibold text-slate-700">Scope audit</div>{scopeDecisions.map((decision) => <div key={decision.decision_id} className="mb-1 rounded bg-slate-50 p-2"><span className="font-semibold">{decision.origin}</span> · {decision.reason} · {decision.confidence.toFixed(2)}</div>)}<div className="mb-2 mt-3 font-semibold text-slate-700">Canonical claims</div>{item.claim_ids.map((id) => <div key={id} className="break-all font-mono">{id}</div>)}<div className="mt-2">Canonical owner: {entities.find((entity) => entity.entity_id === canonicalOwnerId)?.title ?? canonicalOwnerId}</div><div className="mb-2 mt-3 font-semibold text-slate-700">Exact source evidence</div>{item.sources.map((source, index) => { const artifact = sourceArtifacts[source.source_id]; const segments = artifact?.segments.filter((segment) => source.segment_ids.includes(segment.segment_id)) ?? []; return <div key={`${source.source_id}-${index}`} className="mb-2 rounded bg-slate-50 p-2"><div className="font-mono">{source.source_id}</div>{segments.length ? segments.map((segment) => <div key={segment.segment_id} className="mt-2 border-l-2 border-indigo-200 pl-2"><div className="mb-1 font-mono text-[10px] text-slate-400">{segment.segment_id}{segment.speaker ? ` · ${segment.speaker}` : ''}</div><div className="whitespace-pre-wrap text-slate-700">{segment.content}</div></div>) : <div className="mt-1 break-all">{source.segment_ids.join(', ')}</div>}</div>; })}{item.links.length > 0 && <div className="mt-2">Linked entities: {item.links.map((link) => link.title).join(', ')}</div>}<div className="mt-4 grid gap-2 rounded-lg border border-slate-200 p-3 md:grid-cols-[1fr_1fr_auto]"><select value={owner} onChange={(event) => changeOwner(event.target.value)} className="rounded border-slate-200 text-xs">{ownerChoices.map((entity) => <option key={entity.entity_id} value={entity.entity_id}>{entity.title}</option>)}</select><select value={section} onChange={(event) => setSection(event.target.value)} className="rounded border-slate-200 text-xs">{sectionChoices.map((key) => <option key={key} value={key}>{key.replaceAll('_', ' ')}</option>)}</select><button onClick={move} className="rounded bg-indigo-600 px-3 py-2 font-semibold text-white">Move</button></div></div>;
}

function ReviewQueue({ proposals, entities, onReview }: { proposals: OrganizationProposalArtifact[]; entities: EntityRecord[]; onReview: (id: string, decision: 'approve' | 'reject') => void }) {
  const name = (id?: string | null) => entities.find((entity) => entity.entity_id === id)?.title ?? id ?? 'unknown';
  if (!proposals.length) return <p className="p-4 text-sm text-slate-400">Nothing needs organization review.</p>;
  return <div className="space-y-3 p-2">{proposals.map((proposal) => <article key={proposal.proposal_id} className="rounded-xl border border-amber-200 bg-amber-50 p-3"><div className="text-xs font-bold uppercase text-amber-700">{proposal.proposal_type.replace('_', ' ')}</div><p className="mt-2 text-sm text-slate-700">{proposal.explanation}</p><p className="mt-2 text-xs text-slate-500">{proposal.proposal_type === 'merge_entities' ? `${name(proposal.source_entity_id)} → ${name(proposal.target_entity_id)}` : `${proposal.claim_id} → ${name(proposal.proposed_owner_entity_id)}`}</p><div className="mt-3 flex gap-2"><button onClick={() => onReview(proposal.proposal_id, 'approve')} className="rounded bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white">Approve</button><button onClick={() => onReview(proposal.proposal_id, 'reject')} className="rounded bg-white px-3 py-1.5 text-xs font-semibold text-slate-600">Reject</button></div></article>)}</div>;
}

function CurationPanel({ entity, entities, ontology, claimIds, onDone, onClose, selectedClaims, setSelectedClaims }: { entity: EntityRecord; entities: EntityRecord[]; ontology: MemoryOntology; claimIds: string[]; onDone: (slug?: string | null) => Promise<void>; onClose: () => void; selectedClaims: string[]; setSelectedClaims: (ids: string[]) => void }) {
  const [title, setTitle] = useState(entity.title); const [slug, setSlug] = useState(entity.slug);
  const [aliases, setAliases] = useState(entity.aliases.join(', ')); const [type, setType] = useState<PageType>(entity.entity_type);
  const [mergeTarget, setMergeTarget] = useState(''); const [splitTitle, setSplitTitle] = useState(''); const [splitType, setSplitType] = useState<PageType>('topic');
  const save = async () => { await api.patch(`/memory/entities/${entity.entity_id}`, { title, slug, aliases: aliases.split(',').map((value) => value.trim()).filter(Boolean), entity_type: type }); await onDone(slug); onClose(); };
  const archive = async () => { await api.post(`/memory/entities/${entity.entity_id}/archive`); await onDone(null); onClose(); };
  const merge = async () => { if (!mergeTarget) return; await api.post(`/memory/entities/${entity.entity_id}/merge`, { target_entity_id: mergeTarget }); const target = entities.find((value) => value.entity_id === mergeTarget); await onDone(target?.slug); onClose(); };
  const split = async () => { if (!splitTitle || !selectedClaims.length) return; const response = await api.post(`/memory/entities/${entity.entity_id}/split`, { claim_ids: selectedClaims, title: splitTitle, entity_type: splitType, aliases: [] }); setSelectedClaims([]); await onDone(response.data.entity.slug); onClose(); };
  const selectedDefinition = ontology.entity_types.find((definition) => definition.key === type);
  return <div className="mb-8 rounded-2xl border border-indigo-100 bg-indigo-50/50 p-5"><div className="mb-4 flex items-center justify-between"><h2 className="font-bold text-slate-900">Curate organization</h2><button onClick={onClose}><X size={18} /></button></div><div className="grid gap-3 md:grid-cols-2"><input value={title} onChange={(event) => setTitle(event.target.value)} className="rounded-lg border-slate-200 text-sm" placeholder="Title" /><input value={slug} onChange={(event) => setSlug(event.target.value)} className="rounded-lg border-slate-200 text-sm" placeholder="Slug" /><input value={aliases} onChange={(event) => setAliases(event.target.value)} className="rounded-lg border-slate-200 text-sm" placeholder="Aliases, comma separated" /><select value={type} disabled={entity.entity_id === 'you'} onChange={(event) => setType(event.target.value as PageType)} className="rounded-lg border-slate-200 text-sm">{ontology.entity_types.map((definition) => <option key={definition.key} value={definition.key}>{definition.label}</option>)}</select></div><button onClick={save} className="mt-3 rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white">Save identity</button>
    {entity.entity_id !== 'you' && <div className="mt-5 grid gap-4 border-t border-indigo-100 pt-5 md:grid-cols-3"><div><div className="mb-2 text-xs font-bold uppercase text-slate-500">Lifecycle</div><button onClick={archive} className="flex items-center gap-2 rounded-lg bg-white px-3 py-2 text-xs font-semibold text-slate-600"><Archive size={14} /> Archive</button></div><div><div className="mb-2 text-xs font-bold uppercase text-slate-500">Merge</div><select value={mergeTarget} onChange={(event) => setMergeTarget(event.target.value)} className="w-full rounded-lg border-slate-200 text-xs"><option value="">Choose target…</option>{entities.filter((value) => value.entity_id !== entity.entity_id && value.status === 'active' && value.entity_type === entity.entity_type).map((value) => <option key={value.entity_id} value={value.entity_id}>{value.title}</option>)}</select><button onClick={merge} className="mt-2 flex items-center gap-2 rounded bg-white px-3 py-2 text-xs"><GitMerge size={14} /> Merge</button></div><div><div className="mb-2 text-xs font-bold uppercase text-slate-500">Split {selectedClaims.length}/{claimIds.length}</div><input value={splitTitle} onChange={(event) => setSplitTitle(event.target.value)} className="w-full rounded-lg border-slate-200 text-xs" placeholder="New page title" /><select value={splitType} onChange={(event) => setSplitType(event.target.value as PageType)} className="mt-2 w-full rounded-lg border-slate-200 text-xs">{ontology.entity_types.filter((definition) => definition.discoverable).map((definition) => <option key={definition.key} value={definition.key}>{definition.label}</option>)}</select><button onClick={split} className="mt-2 flex items-center gap-2 rounded bg-white px-3 py-2 text-xs"><Split size={14} /> Split selected</button></div></div>}
    <div className="mt-3 text-[11px] text-slate-400">Allowed sections after type changes: {selectedDefinition?.sections.map((section) => section.key).join(', ') ?? ''}</div></div>;
}
