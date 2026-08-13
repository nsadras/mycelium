import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Database,
  FileArchive,
  FileJson,
  FileText,
  GitCompareArrows,
  Layers3,
  Loader2,
  RefreshCw,
  Search,
  ThumbsDown,
  ThumbsUp,
} from 'lucide-react';
import api, {
  type ArtifactOverview,
  type ArtifactSource,
  type ArtifactSourceSummary,
  type ChatEpisodeState,
  type DreamRunArtifact,
  type EpisodeArtifact,
  type MemoryClaimArtifact,
  type ReconsolidationProposalArtifact,
  type StoredMemoryFile,
  type StoredMemoryFiles,
} from '../lib/api';

type InspectorTab = 'overview' | 'chat' | 'sources' | 'episodes' | 'claims' | 'reconsolidation' | 'dream-runs' | 'files';
type StoredFileGroup = 'index' | 'archive';
type SelectedFile = StoredMemoryFile & { group: StoredFileGroup };

const tabs: { id: InspectorTab; label: string; icon: typeof Database }[] = [
  { id: 'overview', label: 'Overview', icon: Database },
  { id: 'chat', label: 'Chat state', icon: Layers3 },
  { id: 'sources', label: 'Sources', icon: FileText },
  { id: 'episodes', label: 'Episodes', icon: Layers3 },
  { id: 'claims', label: 'Claims', icon: FileJson },
  { id: 'reconsolidation', label: 'Reconciliation', icon: GitCompareArrows },
  { id: 'dream-runs', label: 'Dream runs', icon: FileJson },
  { id: 'files', label: 'Stored files', icon: FileArchive },
];

function formatDate(value?: string | null) {
  if (!value) return 'Unknown';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function percentage(value: number) {
  return `${Math.round(value * 100)}%`;
}

function humanize(value: string) {
  return value.replaceAll('_', ' ');
}

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded-lg bg-slate-950 p-3 text-xs leading-relaxed text-slate-300">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function EmptyState({ children }: { children: string }) {
  return <div className="p-8 text-center text-sm text-slate-400">{children}</div>;
}

function Badge({ children, tone = 'slate' }: { children: React.ReactNode; tone?: 'slate' | 'green' | 'amber' | 'red' | 'indigo' }) {
  const colors = {
    slate: 'bg-slate-100 text-slate-600',
    green: 'bg-emerald-50 text-emerald-700',
    amber: 'bg-amber-50 text-amber-700',
    red: 'bg-rose-50 text-rose-700',
    indigo: 'bg-indigo-50 text-indigo-700',
  };
  return <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${colors[tone]}`}>{children}</span>;
}

export default function MemoryInspector({ refreshKey = 0 }: { refreshKey?: number }) {
  const [activeTab, setActiveTab] = useState<InspectorTab>('overview');
  const [overview, setOverview] = useState<ArtifactOverview | null>(null);
  const [chatEpisodes, setChatEpisodes] = useState<ChatEpisodeState[]>([]);
  const [sources, setSources] = useState<ArtifactSourceSummary[]>([]);
  const [episodes, setEpisodes] = useState<EpisodeArtifact[]>([]);
  const [claims, setClaims] = useState<MemoryClaimArtifact[]>([]);
  const [proposals, setProposals] = useState<ReconsolidationProposalArtifact[]>([]);
  const [dreamRuns, setDreamRuns] = useState<DreamRunArtifact[]>([]);
  const [files, setFiles] = useState<StoredMemoryFiles | null>(null);
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [selectedChatId, setSelectedChatId] = useState<string | null>(null);
  const [selectedSource, setSelectedSource] = useState<ArtifactSource | null>(null);
  const [failedSourceId, setFailedSourceId] = useState<string | null>(null);
  const [selectedEpisodeId, setSelectedEpisodeId] = useState<string | null>(null);
  const [selectedClaimId, setSelectedClaimId] = useState<string | null>(null);
  const [selectedDreamRunId, setSelectedDreamRunId] = useState<string | null>(null);
  const [selectedProposalId, setSelectedProposalId] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<SelectedFile | null>(null);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [reviewNote, setReviewNote] = useState('');
  const [reviewing, setReviewing] = useState<'approve' | 'reject' | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [overviewResponse, chatResponse, sourceResponse, episodeResponse, claimResponse, proposalResponse, dreamRunResponse, fileResponse] = await Promise.all([
          api.get<ArtifactOverview>('/memory/artifacts/overview'),
          api.get<ChatEpisodeState[]>('/memory/artifacts/chat-episodes'),
          api.get<ArtifactSourceSummary[]>('/memory/artifacts/sources'),
          api.get<EpisodeArtifact[]>('/memory/artifacts/episodes'),
          api.get<MemoryClaimArtifact[]>('/memory/artifacts/claims'),
          api.get<ReconsolidationProposalArtifact[]>('/memory/artifacts/reconsolidation-proposals'),
          api.get<DreamRunArtifact[]>('/memory/artifacts/dream-runs'),
          api.get<StoredMemoryFiles>('/memory/artifacts/files'),
        ]);
        const orderedSources = [...sourceResponse.data].sort((a, b) => b.recorded_at.localeCompare(a.recorded_at));
        setOverview(overviewResponse.data);
        setChatEpisodes(chatResponse.data);
        setSources(orderedSources);
        setEpisodes(episodeResponse.data);
        setClaims(claimResponse.data);
        const orderedProposals = [...proposalResponse.data].sort((a, b) => {
          if (a.status === 'pending' && b.status !== 'pending') return -1;
          if (b.status === 'pending' && a.status !== 'pending') return 1;
          return b.created_at.localeCompare(a.created_at);
        });
        setProposals(orderedProposals);
        setDreamRuns(dreamRunResponse.data);
        setFiles(fileResponse.data);
        setSelectedSourceId(orderedSources[0]?.source_id ?? null);
        setSelectedChatId(chatResponse.data[0]?.session_id ?? null);
        setSelectedEpisodeId(episodeResponse.data[0]?.episode_id ?? null);
        setSelectedClaimId(claimResponse.data[0]?.claim_id ?? null);
        setSelectedDreamRunId(dreamRunResponse.data[0]?.run_id ?? null);
        setSelectedProposalId(orderedProposals[0]?.proposal_id ?? null);
        const initialFile = fileResponse.data.wiki_index;
        setSelectedFile(initialFile ? { ...initialFile, group: 'index' } : null);
      } catch (loadError) {
        console.error('Failed to load memory artifacts', loadError);
        setError('The memory artifacts could not be loaded. Check the backend logs.');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [refreshKey, reloadKey]);

  useEffect(() => {
    if (!selectedSourceId) {
      return;
    }
    let cancelled = false;
    api.get<ArtifactSource>(`/memory/artifacts/sources/${encodeURIComponent(selectedSourceId)}`)
      .then((response) => {
        if (!cancelled) {
          setSelectedSource(response.data);
          setFailedSourceId(null);
        }
      })
      .catch((sourceError) => {
        console.error('Failed to load source artifact', sourceError);
        if (!cancelled) setFailedSourceId(selectedSourceId);
      })
    return () => { cancelled = true; };
  }, [selectedSourceId]);

  const query = search.trim().toLowerCase();
  const filteredSources = sources.filter((source) =>
    [source.source_id, source.source_type, source.session_id, ...source.participants]
      .some((value) => value.toLowerCase().includes(query))
  );
  const filteredChatEpisodes = chatEpisodes.filter((session) =>
    [session.session_id, session.query, JSON.stringify(session.active_episode), JSON.stringify(session.encoded_episodes)]
      .some((value) => value.toLowerCase().includes(query))
  );
  const filteredEpisodes = episodes.filter((episode) =>
    [episode.episode_id, episode.source_id, episode.source_type, episode.extraction_status, ...episode.participants]
      .some((value) => value.toLowerCase().includes(query))
  );
  const filteredClaims = claims.filter((claim) =>
    [claim.claim_id, claim.text, claim.kind, claim.claim_type, claim.dream_disposition, claim.predicate ?? '', claim.placement?.owner_entity_id ?? '']
      .some((value) => value.toLowerCase().includes(query))
  );
  const filteredDreamRuns = dreamRuns.filter((run) =>
    [run.run_id, run.status, ...run.source_ids, ...run.claim_decisions.flatMap((decision) => [decision.claim_id, decision.disposition, decision.reason])]
      .some((value) => value.toLowerCase().includes(query))
  );
  const filteredProposals = proposals.filter((proposal) =>
    [proposal.proposal_id, proposal.incoming_claim_id, proposal.target_claim_id, proposal.proposed_relation, proposal.status, proposal.explanation]
      .some((value) => value.toLowerCase().includes(query))
  );
  const allFiles = useMemo<SelectedFile[]>(() => {
    if (!files) return [];
    return [
      ...(files.wiki_index ? [{ ...files.wiki_index, group: 'index' as const }] : []),
      ...files.archived_pages.map((file) => ({ ...file, group: 'archive' as const })),
    ];
  }, [files]);
  const filteredFiles = allFiles.filter((file) =>
    `${file.group} ${file.filename} ${file.content}`.toLowerCase().includes(query)
  );

  const selectedEpisode = episodes.find((episode) => episode.episode_id === selectedEpisodeId) ?? null;
  const selectedChatEpisode = chatEpisodes.find((session) => session.session_id === selectedChatId) ?? null;
  const selectedClaim = claims.find((claim) => claim.claim_id === selectedClaimId) ?? null;
  const selectedDreamRun = dreamRuns.find((run) => run.run_id === selectedDreamRunId) ?? null;
  const selectedProposal = proposals.find((proposal) => proposal.proposal_id === selectedProposalId) ?? null;
  const proposalIncomingClaim = claims.find((claim) => claim.claim_id === selectedProposal?.incoming_claim_id) ?? null;
  const proposalTargetClaim = claims.find((claim) => claim.claim_id === selectedProposal?.target_claim_id) ?? null;
  const claimedSegmentIds = useMemo(() => new Set(
    claims.flatMap((claim) => claim.provenance.flatMap((item) => item.segment_ids))
  ), [claims]);
  const ignoredSegmentIds = useMemo(() => new Set(
    episodes.flatMap((episode) => episode.ignored_segment_ids)
  ), [episodes]);

  const selectSource = (sourceId: string) => {
    setSelectedSourceId(sourceId);
    setSearch('');
    setActiveTab('sources');
  };
  const selectClaim = (claimId: string) => {
    setSelectedClaimId(claimId);
    setSearch('');
    setActiveTab('claims');
  };
  const selectTab = (tab: InspectorTab) => {
    setSearch('');
    setActiveTab(tab);
  };
  const reviewProposal = async (decision: 'approve' | 'reject') => {
    if (!selectedProposal) return;
    setReviewing(decision);
    try {
      await api.post(
        `/memory/reconsolidation/proposals/${encodeURIComponent(selectedProposal.proposal_id)}/${decision}`,
        { reviewer_note: reviewNote.trim() || null },
      );
      setReviewNote('');
      setReloadKey((current) => current + 1);
    } catch (reviewError) {
      console.error(`Failed to ${decision} reconsolidation proposal`, reviewError);
      alert(`The proposal could not be ${decision === 'approve' ? 'approved' : 'rejected'}. It may already have been reviewed or become stale.`);
    } finally {
      setReviewing(null);
    }
  };

  if (loading) {
    return <div className="flex flex-1 items-center justify-center bg-white text-slate-500"><Loader2 className="mr-2 animate-spin" /> Loading memory artifacts</div>;
  }

  if (error) {
    return <div className="flex flex-1 items-center justify-center bg-white text-rose-600"><AlertTriangle className="mr-2" /> {error}</div>;
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-white text-slate-900">
      <header className="shrink-0 border-b border-slate-200 px-4 py-4 md:px-6">
        <div className="flex flex-col justify-between gap-3 lg:flex-row lg:items-center">
          <div>
            <h1 className="flex items-center gap-2 text-xl font-bold"><Database className="text-indigo-600" size={21} /> Memory Inspector</h1>
            <p className="mt-1 text-xs text-slate-500">Raw sources, extraction manifests, atomic claims, provenance, and stored memory files.</p>
          </div>
          <div className="flex max-w-full items-center gap-2">
            <nav className="flex max-w-full gap-1 overflow-x-auto rounded-lg bg-slate-100 p-1">
              {tabs.map((tab) => {
                const Icon = tab.icon;
                return (
                  <button
                    key={tab.id}
                    onClick={() => selectTab(tab.id)}
                    className={`flex shrink-0 items-center gap-1.5 rounded-md px-3 py-2 text-xs font-semibold transition-colors ${activeTab === tab.id ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-800'}`}
                  >
                    <Icon size={14} /> {tab.label}
                  </button>
                );
              })}
            </nav>
            <button
              type="button"
              onClick={() => setReloadKey((current) => current + 1)}
              title="Reload artifacts from disk"
              className="shrink-0 rounded-lg border border-slate-200 p-2 text-slate-500 transition-colors hover:bg-slate-50 hover:text-indigo-700"
            >
              <RefreshCw size={16} />
            </button>
          </div>
        </div>
      </header>

      {activeTab === 'overview' && overview && (
        <div className="flex-1 overflow-y-auto p-4 md:p-8">
          <div className="mx-auto max-w-6xl space-y-6">
            <section className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-6">
              {[
                ['Sources', overview.coverage.sources],
                ['Episodes', overview.coverage.episodes],
                ['Claims', overview.coverage.claims],
                ['Dream runs', overview.dream_audit.runs],
                ['Suppressed', overview.coverage.suppressed_claims],
                ['Segments', overview.coverage.segments],
                ['Pending reviews', overview.reconsolidation_proposals.pending ?? 0],
                ['Archived pages', overview.archived_pages],
              ].map(([label, value]) => (
                <div key={label} className="rounded-xl border border-slate-200 p-4">
                  <div className="text-2xl font-bold text-slate-900">{value}</div>
                  <div className="mt-1 text-xs font-medium text-slate-500">{label}</div>
                </div>
              ))}
            </section>

            <section className="grid gap-4 lg:grid-cols-2">
              <div className="rounded-xl border border-slate-200 p-5">
                <div className="mb-4 flex items-center justify-between">
                  <h2 className="font-bold">Extraction coverage</h2>
                  <Badge tone={overview.coverage.accounted_coverage === 1 ? 'green' : 'amber'}>{percentage(overview.coverage.accounted_coverage)} accounted</Badge>
                </div>
                <div className="space-y-4">
                  {[
                    ['Claimed segments', overview.coverage.claimed_segments, overview.coverage.segment_coverage],
                    ['Ignored segments', overview.coverage.ignored_segments, overview.coverage.segments ? overview.coverage.ignored_segments / overview.coverage.segments : 0],
                    ['All accounted segments', overview.coverage.accounted_segments, overview.coverage.accounted_coverage],
                  ].map(([label, count, ratio]) => (
                    <div key={label as string}>
                      <div className="mb-1 flex justify-between text-xs"><span>{label}</span><span className="font-semibold">{count} · {percentage(ratio as number)}</span></div>
                      <div className="h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-indigo-500" style={{ width: percentage(ratio as number) }} /></div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-xl border border-slate-200 p-5">
                <div className="mb-4 flex items-center gap-2">
                  {overview.integrity.healthy ? <CheckCircle2 className="text-emerald-600" size={20} /> : <AlertTriangle className="text-rose-600" size={20} />}
                  <h2 className="font-bold">Referential integrity</h2>
                  <Badge tone={overview.integrity.healthy ? 'green' : 'red'}>{overview.integrity.healthy ? 'Healthy' : 'Issues found'}</Badge>
                </div>
                <div className="space-y-2">
                  {Object.entries(overview.integrity.issues).map(([name, values]) => (
                    <div key={name} className="flex items-start justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2 text-xs">
                      <span className="font-medium text-slate-600">{humanize(name)}</span>
                      {values.length === 0 ? <span className="text-emerald-600">None</span> : <span className="text-right text-rose-600">{values.join(', ')}</span>}
                    </div>
                  ))}
                </div>
              </div>
            </section>

            <section className="rounded-xl border border-slate-200 p-5">
              <div className="mb-3 flex items-center gap-2">
                <h2 className="font-bold">Short-term memory</h2>
                <Badge tone={overview.short_term_memory.ready ? 'amber' : 'slate'}>{overview.short_term_memory.ready ? 'Dream ready' : 'Accumulating'}</Badge>
              </div>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                {[
                  ['Pending', overview.short_term_memory.pending_claims],
                  ['Deferred', overview.short_term_memory.deferred_claims],
                  ['Retryable failures', overview.short_term_memory.retryable_failures],
                  ['Total queued', overview.short_term_memory.total_claims],
                ].map(([label, value]) => <div key={label} className="rounded-lg bg-slate-50 p-3"><div className="text-lg font-bold">{value}</div><div className="text-xs text-slate-500">{label}</div></div>)}
              </div>
              <div className="mt-3 text-xs text-slate-500">Triggers: {overview.short_term_memory.reasons.map(humanize).join(', ') || 'none'} · oldest pending {formatDate(overview.short_term_memory.oldest_pending_at)}</div>
            </section>

            <section className="rounded-xl border border-slate-200 p-5">
              <h2 className="mb-3 font-bold">Wiki projection</h2>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
                {[
                  ['Assignments', overview.projection.page_assignments],
                  ['Assigned claims', overview.projection.assigned_claims],
                  ['Multi-page claims', overview.projection.multi_page_claims],
                  ['Average pages / claim', overview.projection.average_pages_per_claim.toFixed(2)],
                  ['Maximum pages / claim', overview.projection.max_pages_per_claim],
                ].map(([label, value]) => <div key={label} className="rounded-lg bg-slate-50 p-3"><div className="text-lg font-bold">{value}</div><div className="text-xs text-slate-500">{label}</div></div>)}
              </div>
            </section>

            <section className="rounded-xl border border-slate-200 p-5">
              <h2 className="mb-3 font-bold">Claim dispositions</h2>
              <div className="flex flex-wrap gap-2">
                {Object.entries(overview.dream_audit.claim_dispositions).map(([disposition, count]) => (
                  <Badge key={disposition} tone={disposition === 'routed' ? 'green' : disposition === 'routing_failed' ? 'red' : disposition === 'pending' || disposition === 'deferred' ? 'amber' : 'slate'}>
                    {humanize(disposition)} · {count}
                  </Badge>
                ))}
                {!Object.keys(overview.dream_audit.claim_dispositions).length && <span className="text-sm text-slate-400">No claims.</span>}
              </div>
            </section>

            <section className="rounded-xl border border-slate-200 p-5">
              <h2 className="mb-3 font-bold">Extraction warnings</h2>
              <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                {[
                  ['Unassigned segments', overview.coverage.unassigned_segment_ids],
                  ['Unaccounted segments', overview.coverage.unaccounted_segment_ids],
                  ['Unplaced claims', overview.coverage.unplaced_claim_ids],
                  ['Unresolved provenance', overview.coverage.unresolved_provenance_ids],
                  ['Failed episodes', overview.coverage.failed_episode_ids],
                  ['Partial episodes', overview.coverage.partial_episode_ids],
                ].map(([label, values]) => (
                  <div key={label as string} className="rounded-lg bg-slate-50 p-3">
                    <div className="text-xs font-bold text-slate-600">{label}</div>
                    <div className={`mt-1 break-all text-xs ${(values as string[]).length ? 'text-amber-700' : 'text-slate-400'}`}>{(values as string[]).join(', ') || 'None'}</div>
                  </div>
                ))}
              </div>
            </section>
          </div>
        </div>
      )}

      {activeTab !== 'overview' && (
        <div className="flex min-h-0 flex-1 flex-col md:flex-row">
          <aside className="flex h-64 w-full shrink-0 flex-col border-b border-slate-200 bg-slate-50 md:h-full md:w-80 md:border-b-0 md:border-r">
            <div className="border-b border-slate-200 p-3">
              <div className="relative">
                <Search className="absolute left-3 top-2.5 text-slate-400" size={15} />
                <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={`Search ${activeTab}…`} className="w-full rounded-lg border border-slate-200 bg-white py-2 pl-9 pr-3 text-sm outline-none focus:ring-2 focus:ring-indigo-500" />
              </div>
            </div>
            <div className="flex-1 space-y-1 overflow-y-auto p-2">
              {activeTab === 'chat' && filteredChatEpisodes.map((session) => (
                <button key={session.session_id} onClick={() => setSelectedChatId(session.session_id)} className={`w-full rounded-lg p-3 text-left ${selectedChatId === session.session_id ? 'bg-indigo-100 text-indigo-900' : 'hover:bg-white'}`}>
                  <div className="truncate text-sm font-semibold">{session.query}</div>
                  <div className="mt-1 flex justify-between text-[11px] text-slate-500"><span>{session.session_id}</span><span>{session.encoded_episodes.length} encoded</span></div>
                </button>
              ))}
              {activeTab === 'sources' && filteredSources.map((source) => (
                <button key={source.source_id} onClick={() => setSelectedSourceId(source.source_id)} className={`w-full rounded-lg p-3 text-left ${selectedSourceId === source.source_id ? 'bg-indigo-100 text-indigo-900' : 'hover:bg-white'}`}>
                  <div className="truncate text-sm font-semibold">{source.session_id || source.source_id}</div>
                  <div className="mt-1 flex justify-between text-[11px] text-slate-500"><span>{source.source_type}</span><span>{source.segment_count} segments</span></div>
                </button>
              ))}
              {activeTab === 'episodes' && filteredEpisodes.map((episode) => (
                <button key={episode.episode_id} onClick={() => setSelectedEpisodeId(episode.episode_id)} className={`w-full rounded-lg p-3 text-left ${selectedEpisodeId === episode.episode_id ? 'bg-indigo-100 text-indigo-900' : 'hover:bg-white'}`}>
                  <div className="truncate text-sm font-semibold">{episode.episode_id}</div>
                  <div className="mt-1 flex justify-between text-[11px] text-slate-500"><span>{episode.extraction_status}</span><span>{episode.claim_ids.length} claims</span></div>
                </button>
              ))}
              {activeTab === 'claims' && filteredClaims.map((claim) => (
                <button key={claim.claim_id} onClick={() => setSelectedClaimId(claim.claim_id)} className={`w-full rounded-lg p-3 text-left ${selectedClaimId === claim.claim_id ? 'bg-indigo-100 text-indigo-900' : 'hover:bg-white'}`}>
                  <div className="line-clamp-2 text-sm font-semibold">{claim.text}</div>
                  <div className="mt-1 flex justify-between text-[11px] text-slate-500"><span>{humanize(claim.dream_disposition)}</span><span>{claim.placement?.status ?? 'short term'}</span></div>
                </button>
              ))}
              {activeTab === 'reconsolidation' && filteredProposals.map((proposal) => (
                <button key={proposal.proposal_id} onClick={() => { setSelectedProposalId(proposal.proposal_id); setReviewNote(''); }} className={`w-full rounded-lg p-3 text-left ${selectedProposalId === proposal.proposal_id ? 'bg-indigo-100 text-indigo-900' : 'hover:bg-white'}`}>
                  <div className="line-clamp-2 text-sm font-semibold">{humanize(proposal.proposed_relation)}</div>
                  <div className="mt-1 flex justify-between text-[11px] text-slate-500"><span>{proposal.status}</span><span>{formatDate(proposal.created_at)}</span></div>
                </button>
              ))}
              {activeTab === 'dream-runs' && filteredDreamRuns.map((run) => (
                <button key={run.run_id} onClick={() => setSelectedDreamRunId(run.run_id)} className={`w-full rounded-lg p-3 text-left ${selectedDreamRunId === run.run_id ? 'bg-indigo-100 text-indigo-900' : 'hover:bg-white'}`}>
                  <div className="truncate text-sm font-semibold">{formatDate(run.completed_at)}</div>
                  <div className="mt-1 flex justify-between text-[11px] text-slate-500"><span>{run.status}</span><span>{run.claim_decisions.length} decisions</span></div>
                </button>
              ))}
              {activeTab === 'files' && filteredFiles.map((file) => (
                <button key={`${file.group}:${file.filename}`} onClick={() => setSelectedFile(file)} className={`w-full rounded-lg p-3 text-left ${selectedFile?.group === file.group && selectedFile.filename === file.filename ? 'bg-indigo-100 text-indigo-900' : 'hover:bg-white'}`}>
                  <div className="truncate text-sm font-semibold">{file.filename}</div>
                  <div className="mt-1 text-[11px] capitalize text-slate-500">{file.group}</div>
                </button>
              ))}
              {((activeTab === 'chat' && !filteredChatEpisodes.length) || (activeTab === 'sources' && !filteredSources.length) || (activeTab === 'episodes' && !filteredEpisodes.length) || (activeTab === 'claims' && !filteredClaims.length) || (activeTab === 'reconsolidation' && !filteredProposals.length) || (activeTab === 'dream-runs' && !filteredDreamRuns.length) || (activeTab === 'files' && !filteredFiles.length)) && <EmptyState>No matching artifacts.</EmptyState>}
            </div>
          </aside>

          <main className="min-w-0 flex-1 overflow-y-auto">
            {activeTab === 'chat' && (selectedChatEpisode ? (
              <div className="mx-auto max-w-5xl space-y-6 p-5 md:p-8">
                <div>
                  <div className="flex flex-wrap items-center gap-2"><h2 className="text-xl font-bold">{selectedChatEpisode.query}</h2><Badge tone="indigo">UI conversation</Badge></div>
                  <div className="mt-2 font-mono text-xs text-slate-500">{selectedChatEpisode.session_id}</div>
                </div>
                <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-3">
                  <div className="rounded-lg bg-slate-50 p-3"><div className="text-xs text-slate-500">Transcript records</div><strong>{selectedChatEpisode.transcript_turns}</strong></div>
                  <div className="rounded-lg bg-slate-50 p-3"><div className="text-xs text-slate-500">Episode sequence</div><strong>{selectedChatEpisode.episode_seq ?? 'Unknown'}</strong></div>
                  <div className="rounded-lg bg-slate-50 p-3"><div className="text-xs text-slate-500">Encoded episodes</div><strong>{selectedChatEpisode.encoded_episodes.length}</strong></div>
                </div>
                <section><h3 className="mb-2 text-sm font-bold">Active episode and unflushed buffer</h3><JsonBlock value={selectedChatEpisode.active_episode} /></section>
                <section><h3 className="mb-2 text-sm font-bold">Encoded episode history</h3><JsonBlock value={selectedChatEpisode.encoded_episodes} /></section>
              </div>
            ) : <EmptyState>Select a chat session.</EmptyState>)}

            {activeTab === 'sources' && (!selectedSourceId ? <EmptyState>Select a source.</EmptyState> : failedSourceId === selectedSourceId ? <EmptyState>This source could not be loaded.</EmptyState> : selectedSource?.source_id !== selectedSourceId ? <EmptyState>Loading source…</EmptyState> : selectedSource ? (
              <div className="mx-auto max-w-5xl space-y-6 p-5 md:p-8">
                <div>
                  <div className="flex flex-wrap items-center gap-2"><h2 className="break-all text-xl font-bold">{selectedSource.source_id}</h2><Badge tone="indigo">{selectedSource.source_type}</Badge></div>
                  <div className="mt-2 text-xs text-slate-500">Session {selectedSource.session_id} · recorded {formatDate(selectedSource.recorded_at)} · occurred {formatDate(selectedSource.occurred_at)}</div>
                </div>
                <div className="grid gap-3 text-sm md:grid-cols-2">
                  <div className="rounded-lg bg-slate-50 p-3"><span className="font-semibold">Participants:</span> {selectedSource.participants.join(', ') || 'None recorded'}</div>
                  <div className="rounded-lg bg-slate-50 p-3"><span className="font-semibold">Raw log:</span> {selectedSource.raw_log_entry_id ?? 'None'}</div>
                </div>
                {Object.keys(selectedSource.metadata).length > 0 && <section><h3 className="mb-2 text-sm font-bold">Metadata</h3><JsonBlock value={selectedSource.metadata} /></section>}
                <section>
                  <h3 className="mb-3 text-sm font-bold">Segments ({selectedSource.segments.length})</h3>
                  <div className="space-y-3">
                    {selectedSource.segments.map((segment) => {
                      const claimed = claimedSegmentIds.has(segment.segment_id);
                      const ignored = ignoredSegmentIds.has(segment.segment_id);
                      return (
                        <article key={segment.segment_id} className="rounded-xl border border-slate-200 p-4">
                          <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                            <span className="font-mono">#{segment.index} · {segment.segment_id}</span>
                            <Badge tone={claimed ? 'green' : ignored ? 'slate' : 'amber'}>{claimed ? 'claimed' : ignored ? 'ignored' : 'unaccounted'}</Badge>
                            {(segment.speaker || segment.role) && <Badge>{segment.speaker || segment.role}</Badge>}
                            {segment.timestamp && <span>{formatDate(segment.timestamp)}</span>}
                          </div>
                          <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-800">{segment.content}</p>
                          {Object.keys(segment.metadata).length > 0 && <div className="mt-3"><JsonBlock value={segment.metadata} /></div>}
                        </article>
                      );
                    })}
                  </div>
                </section>
              </div>
            ) : <EmptyState>Select a source.</EmptyState>)}

            {activeTab === 'episodes' && (selectedEpisode ? (
              <div className="mx-auto max-w-4xl space-y-6 p-5 md:p-8">
                <div className="flex flex-wrap items-center gap-2"><h2 className="break-all text-xl font-bold">{selectedEpisode.episode_id}</h2><Badge tone={selectedEpisode.extraction_status === 'complete' ? 'green' : selectedEpisode.extraction_status === 'failed' ? 'red' : 'amber'}>{selectedEpisode.extraction_status}</Badge></div>
                <div className="grid gap-3 text-sm md:grid-cols-2">
                  <button onClick={() => selectSource(selectedEpisode.source_id)} className="flex items-center justify-between rounded-lg bg-indigo-50 p-3 text-left text-indigo-700"><span><strong>Source:</strong> {selectedEpisode.source_id}</span><ChevronRight size={15} /></button>
                  <div className="rounded-lg bg-slate-50 p-3"><strong>Type:</strong> {selectedEpisode.source_type}</div>
                  <div className="rounded-lg bg-slate-50 p-3"><strong>Occurred:</strong> {formatDate(selectedEpisode.occurred_at)}</div>
                  <div className="rounded-lg bg-slate-50 p-3"><strong>Participants:</strong> {selectedEpisode.participants.join(', ') || 'None'}</div>
                </div>
                {selectedEpisode.extraction_error && <div className="rounded-lg bg-rose-50 p-4 text-sm text-rose-700"><strong>Extraction error:</strong> {selectedEpisode.extraction_error}</div>}
                <section><h3 className="mb-2 text-sm font-bold">Claims ({selectedEpisode.claim_ids.length})</h3><div className="flex flex-wrap gap-2">{selectedEpisode.claim_ids.map((claimId) => <button key={claimId} onClick={() => selectClaim(claimId)} className="rounded-md bg-indigo-50 px-2 py-1 font-mono text-xs text-indigo-700 hover:bg-indigo-100">{claimId}</button>)}</div></section>
                <section><h3 className="mb-2 text-sm font-bold">Included segments ({selectedEpisode.segment_ids.length})</h3><div className="flex flex-wrap gap-2">{selectedEpisode.segment_ids.map((id) => <Badge key={id}>{id}</Badge>)}</div></section>
                <section><h3 className="mb-2 text-sm font-bold">Ignored segments ({selectedEpisode.ignored_segment_ids.length})</h3><div className="flex flex-wrap gap-2">{selectedEpisode.ignored_segment_ids.map((id) => <Badge key={id}>{id}</Badge>)}</div></section>
              </div>
            ) : <EmptyState>Select an episode.</EmptyState>)}

            {activeTab === 'claims' && (selectedClaim ? (
              <div className="mx-auto max-w-4xl space-y-6 p-5 md:p-8">
                <div><div className="flex flex-wrap gap-2"><Badge tone={selectedClaim.status === 'active' ? 'green' : 'slate'}>{selectedClaim.status}</Badge><Badge tone={selectedClaim.dream_disposition === 'routed' ? 'green' : selectedClaim.dream_disposition === 'routing_failed' ? 'red' : selectedClaim.dream_disposition === 'pending' || selectedClaim.dream_disposition === 'deferred' ? 'amber' : 'slate'}>{humanize(selectedClaim.dream_disposition)}</Badge><Badge tone="indigo">{selectedClaim.claim_type}</Badge><Badge>{selectedClaim.kind}</Badge>{selectedClaim.inferred && <Badge tone="amber">inferred</Badge>}</div><h2 className="mt-4 text-xl font-bold leading-relaxed">{selectedClaim.text}</h2><div className="mt-2 break-all font-mono text-xs text-slate-400">{selectedClaim.claim_id}</div></div>
                <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
                  <div className="rounded-lg bg-slate-50 p-3"><div className="text-xs text-slate-500">Confidence</div><strong>{percentage(selectedClaim.confidence)}</strong></div>
                  <div className="rounded-lg bg-slate-50 p-3"><div className="text-xs text-slate-500">Salience</div><strong>{percentage(selectedClaim.salience)}</strong></div>
                  <div className="rounded-lg bg-slate-50 p-3"><div className="text-xs text-slate-500">Temporal</div><strong>{selectedClaim.temporal_status}</strong></div>
                  <div className="rounded-lg bg-slate-50 p-3"><div className="text-xs text-slate-500">Modality</div><strong>{selectedClaim.evidence_modality}</strong></div>
                </div>
                <div className="grid gap-3 text-sm md:grid-cols-2">
                  <div className="rounded-lg border border-slate-200 p-3"><strong>Predicate:</strong> {selectedClaim.predicate ?? 'None'}<br /><strong>Slot:</strong> {selectedClaim.slot ?? 'None'}<br /><strong>Recorded:</strong> {formatDate(selectedClaim.recorded_at)}<br /><strong>Derivation:</strong> {selectedClaim.derivation_operation ?? 'None'}</div>
                  <div className="rounded-lg border border-slate-200 p-3"><strong>Wiki owner:</strong><div className="mt-2 flex flex-wrap gap-1">{selectedClaim.placement?.owner_entity_id ? <Badge tone="indigo">{selectedClaim.placement.owner_entity_id} · {selectedClaim.placement.section_key}</Badge> : <span className="text-slate-400">Short-term / deferred</span>}</div></div>
                </div>
                <section className="rounded-xl border border-slate-200 p-4">
                  <h3 className="mb-2 text-sm font-bold">Latest Dream decision</h3>
                  <div className="text-sm text-slate-700">{selectedClaim.dream_disposition_reason ?? 'This claim has not been evaluated by Dream.'}</div>
                  <div className="mt-2 break-all font-mono text-xs text-slate-400">{selectedClaim.dream_run_id ?? 'No run'} · {formatDate(selectedClaim.dream_disposition_at)}</div>
                </section>
                <section><h3 className="mb-2 text-sm font-bold">About</h3><JsonBlock value={selectedClaim.about} /></section>
                <section><h3 className="mb-2 text-sm font-bold">Provenance</h3><div className="space-y-2">{selectedClaim.provenance.map((item, index) => <button key={`${item.source_id}:${index}`} onClick={() => selectSource(item.source_id)} className="flex w-full items-center justify-between rounded-lg border border-slate-200 p-3 text-left text-sm hover:bg-slate-50"><span><strong>{item.source_id}</strong><br /><span className="text-xs text-slate-500">{item.segment_ids.join(', ')} · {item.speaker ?? 'unknown speaker'} · {item.evidence_type}</span></span><ChevronRight size={15} /></button>)}</div></section>
                <section className="grid gap-4 md:grid-cols-2"><div><h3 className="mb-2 text-sm font-bold">Facets</h3><JsonBlock value={selectedClaim.facets} /></div><div><h3 className="mb-2 text-sm font-bold">Links</h3><JsonBlock value={selectedClaim.links} /></div></section>
              </div>
            ) : <EmptyState>Select a claim.</EmptyState>)}

            {activeTab === 'reconsolidation' && (selectedProposal ? (
              <div className="mx-auto max-w-5xl space-y-6 p-5 md:p-8">
                <div>
                  <div className="flex flex-wrap items-center gap-2"><h2 className="text-xl font-bold">Proposed {humanize(selectedProposal.proposed_relation)}</h2><Badge tone={selectedProposal.status === 'pending' ? 'amber' : selectedProposal.status === 'applied' ? 'green' : selectedProposal.status === 'stale' ? 'red' : 'slate'}>{selectedProposal.status}</Badge><Badge tone="indigo">{percentage(selectedProposal.confidence)} confidence</Badge></div>
                  <div className="mt-2 break-all font-mono text-xs text-slate-400">{selectedProposal.proposal_id} · {formatDate(selectedProposal.created_at)}</div>
                </div>
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm leading-relaxed text-amber-900">{selectedProposal.explanation}</div>
                <div className="grid gap-4 lg:grid-cols-2">
                  <section className="rounded-xl border border-indigo-200 p-4">
                    <div className="mb-2 text-xs font-bold uppercase tracking-wide text-indigo-600">New source-grounded claim</div>
                    <p className="text-sm leading-relaxed">{proposalIncomingClaim?.text ?? 'Claim artifact missing'}</p>
                    <button onClick={() => selectClaim(selectedProposal.incoming_claim_id)} className="mt-3 font-mono text-xs text-indigo-700 hover:underline">{selectedProposal.incoming_claim_id}</button>
                  </section>
                  <section className="rounded-xl border border-slate-200 p-4">
                    <div className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">Existing canonical claim</div>
                    <p className="text-sm leading-relaxed">{proposalTargetClaim?.text ?? 'Claim artifact missing'}</p>
                    <button onClick={() => selectClaim(selectedProposal.target_claim_id)} className="mt-3 font-mono text-xs text-indigo-700 hover:underline">{selectedProposal.target_claim_id}</button>
                  </section>
                </div>
                <section className="rounded-xl border border-slate-200 p-4 text-sm">
                  <div><strong>Affected entities:</strong> {selectedProposal.affected_entity_ids.join(', ') || 'None assigned'}</div>
                  <div className="mt-2"><strong>Dream run:</strong> {selectedProposal.dream_run_id}</div>
                  {selectedProposal.reviewer_note && <div className="mt-2"><strong>Reviewer note:</strong> {selectedProposal.reviewer_note}</div>}
                  {selectedProposal.application_error && <div className="mt-2 text-rose-700"><strong>Application error:</strong> {selectedProposal.application_error}</div>}
                </section>
                {selectedProposal.status === 'pending' && (
                  <section className="rounded-xl border border-slate-200 p-4">
                    <label className="text-sm font-bold" htmlFor="review-note">Reviewer note</label>
                    <textarea id="review-note" value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} placeholder="Optional rationale for the audit record" className="mt-2 min-h-24 w-full rounded-lg border border-slate-200 p-3 text-sm outline-none focus:ring-2 focus:ring-indigo-500" />
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button disabled={reviewing !== null} onClick={() => void reviewProposal('approve')} className="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"><ThumbsUp size={16} />{reviewing === 'approve' ? 'Applying…' : 'Approve and apply'}</button>
                      <button disabled={reviewing !== null} onClick={() => void reviewProposal('reject')} className="flex items-center gap-2 rounded-lg border border-rose-200 px-4 py-2 text-sm font-semibold text-rose-700 disabled:opacity-50"><ThumbsDown size={16} />{reviewing === 'reject' ? 'Rejecting…' : 'Reject proposal'}</button>
                    </div>
                  </section>
                )}
              </div>
            ) : <EmptyState>Select a reconciliation proposal.</EmptyState>)}

            {activeTab === 'dream-runs' && (selectedDreamRun ? (
              <div className="mx-auto max-w-5xl space-y-6 p-5 md:p-8">
                <div>
                  <div className="flex flex-wrap items-center gap-2"><h2 className="break-all text-xl font-bold">{selectedDreamRun.run_id}</h2><Badge tone={selectedDreamRun.status === 'completed' ? 'green' : selectedDreamRun.status === 'failed' ? 'red' : 'amber'}>{selectedDreamRun.status}</Badge></div>
                  <div className="mt-2 text-xs text-slate-500">{formatDate(selectedDreamRun.started_at)} → {formatDate(selectedDreamRun.completed_at)}</div>
                </div>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div className="rounded-lg bg-slate-50 p-3"><div className="text-xs text-slate-500">Pages created</div><strong>{selectedDreamRun.pages_created}</strong></div>
                  <div className="rounded-lg bg-slate-50 p-3"><div className="text-xs text-slate-500">Pages updated</div><strong>{selectedDreamRun.pages_updated}</strong></div>
                </div>
                <section><h3 className="mb-2 text-sm font-bold">Source outcome</h3><JsonBlock value={{ completed: selectedDreamRun.completed_source_ids, pending: selectedDreamRun.pending_source_ids }} /></section>
                <section>
                  <h3 className="mb-3 text-sm font-bold">Claim decisions ({selectedDreamRun.claim_decisions.length})</h3>
                  <div className="space-y-2">
                    {selectedDreamRun.claim_decisions.map((decision) => (
                      <button key={decision.claim_id} onClick={() => selectClaim(decision.claim_id)} className="flex w-full items-start justify-between gap-4 rounded-lg border border-slate-200 p-3 text-left hover:bg-slate-50">
                        <span className="min-w-0"><span className="break-all font-mono text-xs text-indigo-700">{decision.claim_id}</span><br /><span className="text-xs text-slate-600">{decision.reason}</span>{decision.page_slugs.length > 0 && <span className="mt-1 block text-xs text-slate-400">{decision.page_slugs.join(', ')}</span>}</span>
                        <Badge tone={decision.disposition === 'routed' ? 'green' : decision.disposition === 'routing_failed' ? 'red' : 'slate'}>{humanize(decision.disposition)}</Badge>
                      </button>
                    ))}
                    {!selectedDreamRun.claim_decisions.length && <EmptyState>No claim decisions were made.</EmptyState>}
                  </div>
                </section>
                {selectedDreamRun.failures.length > 0 && <section><h3 className="mb-2 text-sm font-bold">Failures</h3><JsonBlock value={selectedDreamRun.failures} /></section>}
              </div>
            ) : <EmptyState>Select a Dream run.</EmptyState>)}

            {activeTab === 'files' && (selectedFile ? (
              <div className="mx-auto max-w-5xl p-5 md:p-8"><div className="mb-4 flex items-center gap-2"><h2 className="text-xl font-bold">{selectedFile.filename}</h2><Badge tone="indigo">{selectedFile.group}</Badge></div><pre className="overflow-x-auto whitespace-pre-wrap rounded-xl bg-slate-950 p-5 font-mono text-xs leading-relaxed text-slate-300">{selectedFile.content}</pre></div>
            ) : <EmptyState>Select a stored file.</EmptyState>)}
          </main>
        </div>
      )}
    </div>
  );
}
