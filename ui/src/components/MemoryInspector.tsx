import {
  AlertTriangle,
  ClipboardCheck,
  ChevronRight,
  Database,
  FileArchive,
  FileJson,
  FileText,
  GitCompareArrows,
  Layers3,
  Network,
  Rows3,
  Loader2,
  RefreshCw,
  Search,
  ThumbsDown,
  ThumbsUp,
} from 'lucide-react';
import type { InspectorTab, InspectorTarget } from './memory-inspector/types';
import { Badge, EmptyState, JsonBlock } from './memory-inspector/presentation';
import { OverviewPanel } from './memory-inspector/OverviewPanel';
import { ReviewInbox } from './memory-inspector/ReviewInbox';
import { ClaimDetail, EntityDetail, FactDetail, IdentityDetail, OrganizationDetail, SourceDetail } from './memory-inspector/LifecycleDetails';
import { useMemoryInspector } from './memory-inspector/useMemoryInspector';
import { formatDate, humanize, percentage } from './memory-inspector/utils';

const tabs: { id: InspectorTab; label: string; icon: typeof Database }[] = [
  { id: 'overview', label: 'Overview', icon: Database },
  { id: 'review', label: 'Review inbox', icon: ClipboardCheck },
  { id: 'chat', label: 'Chat state', icon: Layers3 },
  { id: 'sources', label: 'Sources', icon: FileText },
  { id: 'episodes', label: 'Episodes', icon: Layers3 },
  { id: 'claims', label: 'Claims', icon: FileJson },
  { id: 'facts', label: 'Facts', icon: Rows3 },
  { id: 'entities', label: 'Entities', icon: Network },
  { id: 'identity', label: 'Identity review', icon: GitCompareArrows },
  { id: 'organization', label: 'Organization', icon: Network },
  { id: 'reconsolidation', label: 'Reconciliation', icon: GitCompareArrows },
  { id: 'dream-runs', label: 'Dream runs', icon: FileJson },
  { id: 'files', label: 'Stored files', icon: FileArchive },
];

export default function MemoryInspector({ refreshKey = 0, target = null }: { refreshKey?: number; target?: InspectorTarget | null }) {
  const {
    activeTab,
    overview,
    ontology,
    entities,
    identityDecisions,
    organizationProposals,
    proposals,
    maturityAssessments,
    filteredSources,
    filteredChatEpisodes,
    filteredEpisodes,
    filteredClaims,
    filteredFacts,
    filteredEntities,
    filteredIdentityDecisions,
    filteredOrganizationProposals,
    filteredDreamRuns,
    filteredProposals,
    filteredFiles,
    selectedSourceId,
    selectedChatId,
    selectedSource,
    selectedEpisodeId,
    selectedClaimId,
    selectedFactId,
    selectedEntityId,
    selectedIdentityDecisionId,
    selectedOrganizationProposalId,
    selectedDreamRunId,
    selectedProposalId,
    selectedFile,
    selectedEpisode,
    selectedChatEpisode,
    selectedClaim,
    selectedFact,
    selectedEntity,
    selectedIdentityDecision,
    selectedOrganizationProposal,
    selectedDreamRun,
    selectedProposal,
    proposalIncomingClaims,
    proposalTargetClaims,
    search,
    loading,
    detailLoading,
    error,
    reviewNote,
    reviewing,
    lifecycleApplying,
    setSelectedSourceId,
    setSelectedChatId,
    setSelectedEpisodeId,
    setSelectedClaimId,
    setSelectedFactId,
    setSelectedEntityId,
    setSelectedIdentityDecisionId,
    setSelectedOrganizationProposalId,
    setSelectedDreamRunId,
    setSelectedProposalId,
    setSelectedFile,
    setSearch,
    setReloadKey,
    setReviewNote,
    selectSource,
    selectClaim,
    selectFact,
    selectEntity,
    selectIdentity,
    selectOrganization,
    selectReconciliation,
    selectDreamRun,
    selectTab,
    reviewProposal,
    reviewOrganizationProposal,
    reviewIdentityDecision,
    correctClaim,
    retractSource,
  } = useMemoryInspector(refreshKey, target);

  if (loading) {
    return <div className="flex flex-1 items-center justify-center bg-white text-slate-500"><Loader2 className="mr-2 animate-spin" /> Loading memory artifacts</div>;
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-white text-slate-900">
      <header className="shrink-0 border-b border-slate-200 px-4 py-4 md:px-6">
        <div className="flex flex-col justify-between gap-3 lg:flex-row lg:items-center">
          <div>
            <h1 className="flex items-center gap-2 text-xl font-bold"><Database className="text-indigo-600" size={21} /> Memory Inspector</h1>
            <p className="mt-1 text-xs text-slate-500">Trace source evidence through episodes, canonical claims, synthesized facts, entity pages, and review decisions.</p>
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

      {error && <div className="flex shrink-0 items-center justify-between gap-3 border-b border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700"><span className="flex items-center gap-2"><AlertTriangle size={16} /> {error}</span><button type="button" onClick={() => setReloadKey((current) => current + 1)} className="rounded-md border border-rose-200 bg-white px-3 py-1 text-xs font-semibold">Retry</button></div>}

      {activeTab === 'overview' && overview && <OverviewPanel overview={overview} />}

      {activeTab === 'review' && <ReviewInbox identities={identityDecisions.filter((item) => item.review_state === 'review_required')} organizations={organizationProposals.filter((item) => item.status === 'pending')} reconciliations={proposals.filter((item) => item.status === 'pending')} provisionalEntities={entities.filter((item) => item.status === 'active' && item.materialization_state === 'provisional')} maturityAssessments={maturityAssessments.filter((item) => item.effective_admission === 'review_required')} selectIdentity={selectIdentity} selectOrganization={selectOrganization} selectReconciliation={selectReconciliation} selectEntity={selectEntity} selectDreamRun={selectDreamRun} />}

      {activeTab !== 'overview' && activeTab !== 'review' && (
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
                  <div className="mt-1 flex justify-between text-[11px] text-slate-500"><span>{episode.extraction_status}</span><span>{episode.claim_count} claims</span></div>
                </button>
              ))}
              {activeTab === 'claims' && filteredClaims.map((claim) => (
                <button key={claim.claim_id} onClick={() => setSelectedClaimId(claim.claim_id)} className={`w-full rounded-lg p-3 text-left ${selectedClaimId === claim.claim_id ? 'bg-indigo-100 text-indigo-900' : 'hover:bg-white'}`}>
                  <div className="line-clamp-2 text-sm font-semibold">{claim.text}</div>
                  <div className="mt-1 flex justify-between text-[11px] text-slate-500"><span>{humanize(claim.dream_disposition)}</span><span>{claim.placement?.status ?? 'short term'}</span></div>
                </button>
              ))}
              {activeTab === 'facts' && filteredFacts.map((fact) => (
                <button key={fact.fact_id} onClick={() => setSelectedFactId(fact.fact_id)} className={`w-full rounded-lg p-3 text-left ${selectedFactId === fact.fact_id ? 'bg-indigo-100 text-indigo-900' : 'hover:bg-white'}`}>
                  <div className="line-clamp-2 text-sm font-semibold">{fact.text}</div>
                  <div className="mt-1 flex justify-between text-[11px] text-slate-500"><span>{fact.synthesis_origin}</span><span>{fact.member_claim_count} claims</span></div>
                </button>
              ))}
              {activeTab === 'entities' && filteredEntities.map((entity) => (
                <button key={entity.entity_id} onClick={() => setSelectedEntityId(entity.entity_id)} className={`w-full rounded-lg p-3 text-left ${selectedEntityId === entity.entity_id ? 'bg-indigo-100 text-indigo-900' : 'hover:bg-white'}`}>
                  <div className="truncate text-sm font-semibold">{entity.title}</div>
                  <div className="mt-1 flex justify-between text-[11px] text-slate-500"><span>{entity.entity_type}</span><span>{entity.status} · {entity.materialization_state}</span></div>
                </button>
              ))}
              {activeTab === 'identity' && filteredIdentityDecisions.map((decision) => (
                <button key={decision.decision_id} onClick={() => { setSelectedIdentityDecisionId(decision.decision_id); setReviewNote(''); }} className={`w-full rounded-lg p-3 text-left ${selectedIdentityDecisionId === decision.decision_id ? 'bg-indigo-100 text-indigo-900' : 'hover:bg-white'}`}>
                  <div className="truncate text-sm font-semibold">{decision.proposed_title}</div>
                  <div className="mt-1 flex justify-between text-[11px] text-slate-500"><span>{humanize(decision.review_state)}</span><span>{decision.proposed_entity_type}</span></div>
                </button>
              ))}
              {activeTab === 'organization' && filteredOrganizationProposals.map((proposal) => (
                <button key={proposal.proposal_id} onClick={() => { setSelectedOrganizationProposalId(proposal.proposal_id); setReviewNote(''); }} className={`w-full rounded-lg p-3 text-left ${selectedOrganizationProposalId === proposal.proposal_id ? 'bg-indigo-100 text-indigo-900' : 'hover:bg-white'}`}>
                  <div className="truncate text-sm font-semibold">{humanize(proposal.proposal_type)}</div>
                  <div className="mt-1 flex justify-between text-[11px] text-slate-500"><span>{proposal.status}</span><span>{formatDate(proposal.created_at)}</span></div>
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
                  <div className="mt-1 flex justify-between text-[11px] text-slate-500"><span>{run.status}</span><span>{run.decision_count} decisions</span></div>
                </button>
              ))}
              {activeTab === 'files' && filteredFiles.map((file) => (
                <button key={`${file.group}:${file.filename}`} onClick={() => setSelectedFile(file)} className={`w-full rounded-lg p-3 text-left ${selectedFile?.group === file.group && selectedFile.filename === file.filename ? 'bg-indigo-100 text-indigo-900' : 'hover:bg-white'}`}>
                  <div className="truncate text-sm font-semibold">{file.filename}</div>
                  <div className="mt-1 text-[11px] capitalize text-slate-500">{file.group}</div>
                </button>
              ))}
              {((activeTab === 'chat' && !filteredChatEpisodes.length) || (activeTab === 'sources' && !filteredSources.length) || (activeTab === 'episodes' && !filteredEpisodes.length) || (activeTab === 'claims' && !filteredClaims.length) || (activeTab === 'facts' && !filteredFacts.length) || (activeTab === 'entities' && !filteredEntities.length) || (activeTab === 'identity' && !filteredIdentityDecisions.length) || (activeTab === 'organization' && !filteredOrganizationProposals.length) || (activeTab === 'reconsolidation' && !filteredProposals.length) || (activeTab === 'dream-runs' && !filteredDreamRuns.length) || (activeTab === 'files' && !filteredFiles.length)) && <EmptyState>No matching artifacts.</EmptyState>}
            </div>
          </aside>

          <main className="relative min-w-0 flex-1 overflow-y-auto">
            {detailLoading && <div className="sticky top-0 z-10 flex items-center justify-center gap-2 border-b border-indigo-100 bg-indigo-50/95 px-4 py-2 text-xs font-semibold text-indigo-700"><Loader2 className="animate-spin" size={14} /> Loading selected artifact…</div>}
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

            {activeTab === 'sources' && (!selectedSourceId ? <EmptyState>Select a source.</EmptyState> : selectedSource?.source_id !== selectedSourceId ? <EmptyState>Loading source…</EmptyState> : selectedSource ? <SourceDetail source={selectedSource} retracting={lifecycleApplying === 'retract'} retractSource={retractSource} /> : <EmptyState>Select a source.</EmptyState>)}

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
                <section><h3 className="mb-2 text-sm font-bold">Segment dispositions ({selectedEpisode.segment_dispositions.length})</h3><div className="space-y-2">{selectedEpisode.segment_dispositions.map((item) => <div key={item.segment_id} className="rounded-lg bg-slate-50 p-3 text-xs"><div className="flex flex-wrap items-center gap-2"><Badge tone={item.disposition === 'claimed' ? 'green' : 'slate'}>{item.disposition}</Badge><span className="font-mono">{item.segment_id}</span></div>{item.claim_ids.length > 0 && <div className="mt-1 text-slate-600">Claims: {item.claim_ids.join(', ')}</div>}{item.reason && <div className="mt-1 text-slate-600">{item.reason}</div>}</div>)}</div></section>
              </div>
            ) : <EmptyState>Select an episode.</EmptyState>)}

            {activeTab === 'claims' && (selectedClaim ? <ClaimDetail claim={selectedClaim} claimTypes={ontology?.claim_types ?? []} selectSource={selectSource} selectFact={selectFact} selectIdentity={selectIdentity} selectReconciliation={selectReconciliation} correcting={lifecycleApplying === 'correct'} correctClaim={correctClaim} /> : <EmptyState>Select a claim.</EmptyState>)}

            {activeTab === 'facts' && (selectedFact ? <FactDetail fact={selectedFact} selectClaim={selectClaim} selectEntity={selectEntity} /> : <EmptyState>Select a consolidated fact.</EmptyState>)}

            {activeTab === 'entities' && (selectedEntity ? <EntityDetail entity={selectedEntity} selectFact={selectFact} selectClaim={selectClaim} /> : <EmptyState>Select an entity.</EmptyState>)}

            {activeTab === 'identity' && (selectedIdentityDecision ? <IdentityDetail decision={selectedIdentityDecision} entities={entities} entityTypes={ontology?.entity_types ?? []} reviewNote={reviewNote} reviewing={reviewing} setReviewNote={setReviewNote} selectClaim={selectClaim} selectEntity={selectEntity} review={reviewIdentityDecision} /> : <EmptyState>Select an identity decision.</EmptyState>)}

            {activeTab === 'organization' && (selectedOrganizationProposal ? <OrganizationDetail proposal={selectedOrganizationProposal} reviewNote={reviewNote} reviewing={reviewing} setReviewNote={setReviewNote} selectClaim={selectClaim} selectEntity={selectEntity} review={reviewOrganizationProposal} /> : <EmptyState>Select an organization proposal.</EmptyState>)}

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
                    <div className="space-y-3">{selectedProposal.incoming_claim_ids.map((claimId) => <div key={claimId}><p className="text-sm leading-relaxed">{proposalIncomingClaims.find((claim) => claim.claim_id === claimId)?.text ?? 'Claim artifact missing'}</p><button onClick={() => selectClaim(claimId)} className="mt-1 font-mono text-xs text-indigo-700 hover:underline">{claimId}</button></div>)}</div>
                  </section>
                  <section className="rounded-xl border border-slate-200 p-4">
                    <div className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">Existing canonical claim</div>
                    <div className="space-y-3">{selectedProposal.target_claim_ids.map((claimId) => <div key={claimId}><p className="text-sm leading-relaxed">{proposalTargetClaims.find((claim) => claim.claim_id === claimId)?.text ?? 'Claim artifact missing'}</p><button onClick={() => selectClaim(claimId)} className="mt-1 font-mono text-xs text-indigo-700 hover:underline">{claimId}</button></div>)}</div>
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
                <section><h3 className="mb-2 text-sm font-bold">Identity maturity proposals and verification ({selectedDreamRun.identity_maturity_assessments.length})</h3><JsonBlock value={selectedDreamRun.identity_maturity_assessments} /></section>
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
              <div className="mx-auto max-w-5xl p-5 md:p-8"><div className="mb-4 flex items-center gap-2"><h2 className="text-xl font-bold">{selectedFile.filename}</h2><Badge tone="indigo">{selectedFile.group}</Badge><Badge>{selectedFile.size.toLocaleString()} bytes</Badge></div>{selectedFile.content === undefined ? <EmptyState>Loading stored file…</EmptyState> : <pre className="overflow-x-auto whitespace-pre-wrap rounded-xl bg-slate-950 p-5 font-mono text-xs leading-relaxed text-slate-300">{selectedFile.content}</pre>}</div>
            ) : <EmptyState>Select a stored file.</EmptyState>)}
          </main>
        </div>
      )}
    </div>
  );
}
