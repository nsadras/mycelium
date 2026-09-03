import { useState } from 'react';
import { ChevronRight, ThumbsDown, ThumbsUp } from 'lucide-react';

import type {
  ArtifactSource,
  ConsolidatedFactDetail,
  EntityArtifactDetail,
  EntityRecord,
  EntityResolutionDecisionArtifact,
  EntityTypeOntology,
  MemoryClaimArtifact,
  OrganizationProposalArtifact,
} from '../../lib/api';
import { Badge, EmptyState, JsonBlock } from './presentation';
import { formatDate, percentage } from './utils';

interface ClaimDetailProps {
  claim: MemoryClaimArtifact;
  claimTypes: string[];
  selectSource: (id: string) => void;
  selectFact: (id: string) => void;
  selectIdentity: (id: string) => void;
  selectReconciliation: (id: string) => void;
  correcting: boolean;
  correctClaim: (text: string, reason: string, fields: { claim_type?: string; predicate?: string | null; temporal_status?: string }) => Promise<void>;
}

export function ClaimDetail({ claim, claimTypes, selectSource, selectFact, selectIdentity, selectReconciliation, correcting, correctClaim }: ClaimDetailProps) {
  return (
    <div className="mx-auto max-w-4xl space-y-6 p-5 md:p-8">
      <div>
        <div className="flex flex-wrap gap-2">
          <Badge tone={claim.status === 'active' ? 'green' : 'slate'}>{claim.status}</Badge>
          <Badge tone={claim.dream_disposition === 'routed' ? 'green' : claim.dream_disposition === 'routing_failed' ? 'red' : claim.dream_disposition === 'pending' || claim.dream_disposition === 'deferred' ? 'amber' : 'slate'}>{claim.dream_disposition.replaceAll('_', ' ')}</Badge>
          <Badge tone="indigo">{claim.claim_type}</Badge>
          {claim.provenance.some((item) => item.evidence_type === 'inferred') && <Badge tone="amber">inferred</Badge>}
        </div>
        <h2 className="mt-4 text-xl font-bold leading-relaxed">{claim.text}</h2>
        <div className="mt-2 break-all font-mono text-xs text-slate-400">{claim.claim_id}</div>
      </div>
      <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-3">
        <div className="rounded-lg bg-slate-50 p-3"><div className="text-xs text-slate-500">Confidence</div><strong>{percentage(claim.confidence)}</strong></div>
        <div className="rounded-lg bg-slate-50 p-3"><div className="text-xs text-slate-500">Temporal</div><strong>{claim.temporal_status}</strong></div>
        <div className="rounded-lg bg-slate-50 p-3"><div className="text-xs text-slate-500">Modality</div><strong>{claim.evidence_modality}</strong></div>
      </div>
      <div className="grid gap-3 text-sm md:grid-cols-2">
        <div className="rounded-lg border border-slate-200 p-3"><strong>Predicate:</strong> {claim.predicate ?? 'None'}<br /><strong>Slot:</strong> {claim.slot ?? 'None'}<br /><strong>Recorded:</strong> {formatDate(claim.recorded_at)}</div>
        <div className="rounded-lg border border-slate-200 p-3"><strong>Wiki owner:</strong><div className="mt-2 flex flex-wrap gap-1">{claim.placement?.owner_entity_id ? <Badge tone="indigo">{claim.placement.owner_entity_id} · {claim.placement.section_key}</Badge> : <span className="text-slate-400">Short-term / deferred</span>}</div></div>
      </div>
      <section className="rounded-xl border border-slate-200 p-4">
        <h3 className="mb-2 text-sm font-bold">Latest Dream decision</h3>
        <div className="text-sm text-slate-700">{claim.dream_disposition_reason ?? 'This claim has not been evaluated by Dream.'}</div>
        {(claim.placement?.identity_blocker_ids ?? []).length > 0 && <div className="mt-3"><div className="text-xs font-semibold uppercase tracking-wide text-amber-700">Unresolved identity blockers</div><div className="mt-2 flex flex-wrap gap-1">{claim.placement!.identity_blocker_ids.map((id) => <button key={id} onClick={() => selectIdentity(id)} className="rounded-md bg-amber-100 px-2 py-1 font-mono text-xs text-amber-800 hover:bg-amber-200">{id}</button>)}</div></div>}
        <div className="mt-2 break-all font-mono text-xs text-slate-400">{claim.dream_run_id ?? 'No run'} · {formatDate(claim.dream_disposition_at)}</div>
      </section>
      <section className="rounded-xl border border-indigo-100 bg-indigo-50/40 p-4">
        <h3 className="mb-3 text-sm font-bold">Claim → fact → wiki lifecycle</h3>
        <div className="space-y-2">
          {(claim.facts ?? []).map((fact) => (
            <button key={fact.fact_id} onClick={() => selectFact(fact.fact_id)} className="flex w-full items-center justify-between rounded-lg bg-white p-3 text-left text-sm ring-1 ring-indigo-100">
              <span><strong>{fact.text}</strong><br /><span className="text-xs text-slate-500">{fact.synthesis_origin} · {fact.owner_entity_id} / {fact.section_key}</span></span><ChevronRight size={15} />
            </button>
          ))}
          {!(claim.facts ?? []).length && <div className="text-sm text-slate-500">No current display fact contains this claim. It remains canonical even when it is pending, deferred, or superseded.</div>}
        </div>
      </section>
      <section><h3 className="mb-2 text-sm font-bold">Scope decision history</h3><JsonBlock value={claim.scope_decisions ?? []} /></section>
      <section><h3 className="mb-2 text-sm font-bold">Resolved entity references</h3><JsonBlock value={claim.entity_references ?? []} /></section>
      {(claim.reconsolidation_proposals ?? []).length > 0 && <section><h3 className="mb-2 text-sm font-bold">Reconciliation history</h3><div className="space-y-2">{claim.reconsolidation_proposals!.map((proposal) => <button key={proposal.proposal_id} onClick={() => selectReconciliation(proposal.proposal_id)} className="flex w-full items-center justify-between rounded-lg border border-slate-200 p-3 text-left"><span><strong className="text-sm">{proposal.proposed_relation.replaceAll('_', ' ')}</strong><br /><span className="text-xs text-slate-500">{proposal.status} · {proposal.explanation}</span></span><ChevronRight size={15} /></button>)}</div></section>}
      <section><h3 className="mb-2 text-sm font-bold">About</h3><JsonBlock value={claim.about} /></section>
      <section><h3 className="mb-2 text-sm font-bold">Provenance</h3><div className="space-y-2">{claim.provenance.map((item, index) => <button key={`${item.source_id}:${index}`} onClick={() => selectSource(item.source_id)} className="flex w-full items-center justify-between rounded-lg border border-slate-200 p-3 text-left text-sm hover:bg-slate-50"><span><strong>{item.source_id}</strong><br /><span className="text-xs text-slate-500">{item.segment_ids.join(', ')} · {item.speaker ?? 'unknown speaker'} · {item.evidence_type}</span></span><ChevronRight size={15} /></button>)}</div></section>
      {claim.status === 'active' && <ClaimCorrectionForm key={claim.claim_id} claim={claim} claimTypes={claimTypes} correcting={correcting} correctClaim={correctClaim} />}
      <section className="grid gap-4 md:grid-cols-2"><div><h3 className="mb-2 text-sm font-bold">Facets</h3><JsonBlock value={claim.facets} /></div><div><h3 className="mb-2 text-sm font-bold">Links</h3><JsonBlock value={claim.links} /></div></section>
    </div>
  );
}

const temporalStatuses = ['past', 'current', 'future', 'recurring', 'atemporal', 'unknown'];

function ClaimCorrectionForm({ claim, claimTypes, correcting, correctClaim }: Pick<ClaimDetailProps, 'claim' | 'claimTypes' | 'correcting' | 'correctClaim'>) {
  const [text, setText] = useState(claim.text);
  const [reason, setReason] = useState('');
  const [claimType, setClaimType] = useState(claim.claim_type);
  const [predicate, setPredicate] = useState(claim.predicate ?? '');
  const [temporalStatus, setTemporalStatus] = useState(claim.temporal_status);
  return <section className="rounded-xl border border-amber-200 bg-amber-50/40 p-4"><h3 className="text-sm font-bold text-amber-950">Correct canonical claim</h3><p className="mt-1 text-xs leading-relaxed text-amber-800">This creates new explicit source evidence, supersedes this claim, preserves its current wiki ownership, and rebuilds its facts and page.</p><label className="mt-4 block text-xs font-semibold text-slate-700" htmlFor="claim-correction-text">Replacement claim</label><textarea id="claim-correction-text" value={text} onChange={(event) => setText(event.target.value)} className="mt-1 min-h-24 w-full rounded-lg border border-slate-200 bg-white p-3 text-sm outline-none focus:ring-2 focus:ring-amber-500" /><div className="mt-3 grid gap-3 md:grid-cols-3"><label className="text-xs font-semibold text-slate-700">Claim type<select value={claimType} onChange={(event) => setClaimType(event.target.value)} className="mt-1 w-full rounded-lg border-slate-200 bg-white text-sm">{claimTypes.map((value) => <option key={value} value={value}>{value}</option>)}</select></label><label className="text-xs font-semibold text-slate-700">Predicate<input value={predicate} onChange={(event) => setPredicate(event.target.value)} placeholder="Optional structured predicate" className="mt-1 w-full rounded-lg border-slate-200 bg-white text-sm" /></label><label className="text-xs font-semibold text-slate-700">Temporal status<select value={temporalStatus} onChange={(event) => setTemporalStatus(event.target.value)} className="mt-1 w-full rounded-lg border-slate-200 bg-white text-sm">{temporalStatuses.map((value) => <option key={value} value={value}>{value}</option>)}</select></label></div><label className="mt-3 block text-xs font-semibold text-slate-700" htmlFor="claim-correction-reason">Reason</label><textarea id="claim-correction-reason" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Why is the current claim incorrect?" className="mt-1 min-h-20 w-full rounded-lg border border-slate-200 bg-white p-3 text-sm outline-none focus:ring-2 focus:ring-amber-500" /><button disabled={correcting || !text.trim() || !reason.trim()} onClick={() => void correctClaim(text, reason, { claim_type: claimType, predicate: predicate.trim() || null, temporal_status: temporalStatus })} className="mt-3 rounded-lg bg-amber-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{correcting ? 'Correcting and rebuilding…' : 'Create corrected claim'}</button></section>;
}

interface SourceDetailProps {
  source: ArtifactSource;
  retracting: boolean;
  retractSource: (reason: string) => Promise<void>;
}

export function SourceDetail({ source, retracting, retractSource }: SourceDetailProps) {
  const [reason, setReason] = useState('');
  return (
    <div className="mx-auto max-w-5xl space-y-6 p-5 md:p-8">
      <div><div className="flex flex-wrap items-center gap-2"><h2 className="break-all text-xl font-bold">{source.source_id}</h2><Badge tone="indigo">{source.source_type}</Badge><Badge tone={source.status === 'active' ? 'green' : 'red'}>{source.status}</Badge></div><div className="mt-2 text-xs text-slate-500">Session {source.session_id} · recorded {formatDate(source.recorded_at)} · occurred {formatDate(source.occurred_at)}</div></div>
      {source.status === 'retracted' && <section className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900"><strong>Retracted {formatDate(source.retracted_at)}</strong><p className="mt-1">{source.retraction_reason}</p></section>}
      <div className="grid gap-3 text-sm md:grid-cols-2"><div className="rounded-lg bg-slate-50 p-3"><span className="font-semibold">Participants:</span> {source.participants.join(', ') || 'None recorded'}</div><div className="rounded-lg bg-slate-50 p-3"><span className="font-semibold">Raw log:</span> {source.raw_log_entry_id ?? 'None'}</div></div>
      {Object.keys(source.metadata).length > 0 && <section><h3 className="mb-2 text-sm font-bold">Metadata</h3><JsonBlock value={source.metadata} /></section>}
      <section><h3 className="mb-3 text-sm font-bold">Segments ({source.segments.length})</h3><div className="space-y-3">{source.segments.map((segment) => { const accounting = source.segment_accounting[segment.segment_id] ?? 'unaccounted'; return <article key={segment.segment_id} className="rounded-xl border border-slate-200 p-4"><div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-slate-500"><span className="font-mono">#{segment.index} · {segment.segment_id}</span><Badge tone={accounting === 'claimed' ? 'green' : accounting === 'source_only' ? 'slate' : 'amber'}>{accounting.replaceAll('_', ' ')}</Badge>{(segment.speaker || segment.role) && <Badge>{segment.speaker || segment.role}</Badge>}{segment.timestamp && <span>{formatDate(segment.timestamp)}</span>}</div><p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-800">{segment.content}</p>{Object.keys(segment.metadata).length > 0 && <div className="mt-3"><JsonBlock value={segment.metadata} /></div>}</article>; })}</div></section>
      {source.status === 'active' && <section className="rounded-xl border border-rose-200 bg-rose-50/40 p-4"><h3 className="text-sm font-bold text-rose-950">Retract source</h3><p className="mt-1 text-xs leading-relaxed text-rose-800">Retraction preserves this evidence for audit, removes claims with no other active support, and rebuilds affected facts and pages.</p><label className="mt-4 block text-xs font-semibold text-slate-700" htmlFor="source-retraction-reason">Reason</label><textarea id="source-retraction-reason" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Why should this source no longer support memory?" className="mt-1 min-h-20 w-full rounded-lg border border-slate-200 bg-white p-3 text-sm outline-none focus:ring-2 focus:ring-rose-500" /><button disabled={retracting || !reason.trim()} onClick={() => void retractSource(reason)} className="mt-3 rounded-lg bg-rose-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{retracting ? 'Retracting and rebuilding…' : 'Retract source'}</button></section>}
    </div>
  );
}

interface FactDetailProps {
  fact: ConsolidatedFactDetail;
  selectClaim: (id: string) => void;
  selectEntity: (id: string) => void;
}

export function FactDetail({ fact, selectClaim, selectEntity }: FactDetailProps) {
  return (
    <div className="mx-auto max-w-5xl space-y-6 p-5 md:p-8">
      <div><div className="flex flex-wrap gap-2"><Badge tone="indigo">{fact.synthesis_origin}</Badge><Badge>{fact.state}</Badge>{fact.manual_text && <Badge tone="amber">manually edited</Badge>}<Badge>{percentage(fact.confidence)}</Badge></div><h2 className="mt-4 text-xl font-bold leading-relaxed">{fact.text}</h2><div className="mt-2 break-all font-mono text-xs text-slate-400">{fact.fact_id}</div></div>
      <section className="rounded-xl border border-indigo-100 bg-indigo-50/40 p-4">
        <h3 className="mb-3 text-sm font-bold">Wiki projection</h3>
        <button onClick={() => selectEntity(fact.owner_entity_id)} className="flex w-full items-center justify-between rounded-lg bg-white p-3 text-left ring-1 ring-indigo-100"><span><strong>{fact.owner.title}</strong><br /><span className="text-xs text-slate-500">{fact.owner_entity_id} · {fact.section_key}</span></span><ChevronRight size={15} /></button>
        {fact.linked_entities.length > 0 && <div className="mt-3 text-xs text-slate-500">Linked entities: {fact.linked_entities.map((entity) => entity.title).join(', ')}</div>}
      </section>
      <section><h3 className="mb-3 text-sm font-bold">Canonical member claims ({fact.claims.length})</h3><div className="space-y-2">{fact.claims.map((claim) => <button key={claim.claim_id} onClick={() => selectClaim(claim.claim_id)} className="flex w-full items-center justify-between rounded-lg border border-slate-200 p-3 text-left"><span><strong className="text-sm">{claim.text}</strong><br /><span className="font-mono text-xs text-slate-400">{claim.claim_id}</span></span><ChevronRight size={15} /></button>)}</div></section>
      <section><h3 className="mb-2 text-sm font-bold">Synthesis rationale</h3><div className="rounded-lg bg-slate-50 p-4 text-sm text-slate-700">{fact.reason}</div></section>
    </div>
  );
}

interface EntityDetailProps {
  entity: EntityArtifactDetail;
  selectFact: (id: string) => void;
  selectClaim: (id: string) => void;
}

export function EntityDetail({ entity, selectFact, selectClaim }: EntityDetailProps) {
  const counts: [string, number][] = [
    ['Claims', entity.placements.length],
    ['Facts', entity.facts.length],
    ['Encounters', entity.encounters.length],
    ['Identity decisions', entity.resolution_decisions.length],
  ];
  return (
    <div className="mx-auto max-w-5xl space-y-6 p-5 md:p-8">
      <div><div className="flex flex-wrap gap-2"><Badge tone="indigo">{entity.entity_type}</Badge><Badge tone={entity.status === 'active' ? 'green' : 'slate'}>{entity.status}</Badge><Badge tone={entity.materialization_state === 'materialized' ? 'green' : 'amber'}>{entity.materialization_state}</Badge>{entity.page?.exists && <Badge tone="green">wiki page</Badge>}</div><h2 className="mt-4 text-2xl font-bold">{entity.title}</h2><div className="mt-2 break-all font-mono text-xs text-slate-400">{entity.entity_id} · {entity.slug}</div>{entity.materialization_state === 'provisional' && <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">This identity is canonical but does not have a wiki page yet. It is waiting for stronger continuity evidence or an explicit identity adjudication.</p>}</div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{counts.map(([label, value]) => <div key={label} className="rounded-lg bg-slate-50 p-3"><div className="text-lg font-bold">{value}</div><div className="text-xs text-slate-500">{label}</div></div>)}</div>
      <section><h3 className="mb-3 text-sm font-bold">Current consolidated facts</h3><div className="space-y-2">{entity.facts.map((fact) => <button key={fact.fact_id} onClick={() => selectFact(fact.fact_id)} className="flex w-full items-center justify-between rounded-lg border border-slate-200 p-3 text-left"><span><strong className="text-sm">{fact.text}</strong><br /><span className="text-xs text-slate-500">{fact.section_key} · {fact.member_claim_ids.length} claims</span></span><ChevronRight size={15} /></button>)}{!entity.facts.length && <EmptyState>No current facts for this entity.</EmptyState>}</div></section>
      <section><h3 className="mb-3 text-sm font-bold">Canonical claim assignments</h3><div className="flex flex-wrap gap-2">{entity.placements.map((placement) => <button key={placement.claim_id} onClick={() => selectClaim(placement.claim_id)} className="rounded-md bg-indigo-50 px-3 py-2 font-mono text-xs text-indigo-700">{placement.claim_id}</button>)}{!entity.placements.length && <span className="text-sm text-slate-500">No claims are assigned to this entity.</span>}</div></section>
      <section><h3 className="mb-2 text-sm font-bold">Identity resolution audit</h3><JsonBlock value={entity.resolution_decisions} /></section>
      <section><h3 className="mb-2 text-sm font-bold">Maturity proposal and verification</h3><div className="space-y-2">{entity.maturity_assessments.map((item) => <article key={item.assessment_id} className="rounded-lg border border-slate-200 p-3 text-sm"><div className="flex flex-wrap gap-2"><Badge tone={item.effective_admission === 'materialized' ? 'green' : 'amber'}>{item.effective_admission.replaceAll('_', ' ')}</Badge><Badge>{item.verifier_verdict}</Badge></div><p className="mt-2 text-slate-700">{item.proposal_reason}</p><p className="mt-1 text-xs text-slate-500">Verifier: {item.verifier_reason}</p><div className="mt-2 font-mono text-[10px] text-slate-400">{item.assessment_id} · {item.dream_run_id}</div></article>)}{!entity.maturity_assessments.length && <EmptyState>No maturity assessment is attached to this entity.</EmptyState>}</div></section>
      <section><h3 className="mb-2 text-sm font-bold">Encounter history</h3><JsonBlock value={entity.encounters} /></section>
    </div>
  );
}

interface IdentityDetailProps {
  decision: EntityResolutionDecisionArtifact;
  entities: EntityRecord[];
  entityTypes: EntityTypeOntology[];
  reviewNote: string;
  reviewing: 'approve' | 'reject' | null;
  setReviewNote: (value: string) => void;
  selectClaim: (id: string) => void;
  selectEntity: (id: string) => void;
  review: (decision: 'approve' | 'reject', overrides?: Record<string, string | null>) => Promise<void>;
}

export function IdentityDetail({ decision, entities, entityTypes, reviewNote, reviewing, setReviewNote, selectClaim, selectEntity, review }: IdentityDetailProps) {
  return (
    <div className="mx-auto max-w-4xl space-y-6 p-5 md:p-8">
      <div>
        <div className="flex flex-wrap gap-2"><Badge tone="indigo">{decision.proposed_entity_type}</Badge><Badge tone={decision.review_state === 'accepted' ? 'green' : decision.review_state === 'review_required' ? 'amber' : 'slate'}>{decision.review_state.replaceAll('_', ' ')}</Badge><Badge>{percentage(decision.confidence)}</Badge></div>
        <h2 className="mt-4 text-xl font-bold">{decision.proposed_title}</h2>
        <div className="mt-2 break-all font-mono text-xs text-slate-400">{decision.decision_id} · {formatDate(decision.created_at)}</div>
      </div>
      <div className="rounded-xl border border-indigo-100 bg-indigo-50/50 p-4 text-sm leading-relaxed text-indigo-950">{decision.reason}</div>
      {decision.proposed_type_reason && <div className="rounded-xl border border-amber-100 bg-amber-50/50 p-4 text-sm leading-relaxed text-amber-950"><strong>Type assessment:</strong> {decision.proposed_type_reason}</div>}
      <section className="grid gap-3 text-sm md:grid-cols-2">
        <div className="rounded-lg bg-slate-50 p-3"><strong>Scope:</strong> {decision.proposed_scope ?? 'Not recorded'}<br /><strong>Page state:</strong> {decision.proposed_page_state ?? 'Not recorded'}</div>
        <div className="rounded-lg bg-slate-50 p-3"><strong>Parent:</strong> {decision.proposed_parent_entity_id ?? 'None'}<br /><strong>Aliases:</strong> {decision.proposed_aliases.join(', ') || 'None'}</div>
      </section>
      {decision.entity_id && <button onClick={() => selectEntity(decision.entity_id!)} className="flex w-full items-center justify-between rounded-lg border border-slate-200 p-3 text-left"><span><strong>Proposed canonical identity</strong><br /><span className="font-mono text-xs text-slate-500">{decision.entity_id}</span></span><ChevronRight size={15} /></button>}
      <section><h3 className="mb-2 text-sm font-bold">Identity-defining claims</h3><div className="flex flex-wrap gap-2">{decision.identity_evidence_claim_ids.map((id) => <button key={id} onClick={() => selectClaim(id)} className="rounded-md bg-amber-50 px-3 py-2 font-mono text-xs text-amber-700">{id}</button>)}</div></section>
      <section><h3 className="mb-2 text-sm font-bold">All supporting canonical claims</h3><div className="flex flex-wrap gap-2">{decision.supporting_claim_ids.map((id) => <button key={id} onClick={() => selectClaim(id)} className="rounded-md bg-indigo-50 px-3 py-2 font-mono text-xs text-indigo-700">{id}</button>)}</div></section>
      {decision.reviewer_note && <section className="rounded-lg bg-slate-50 p-4 text-sm"><strong>Reviewer note:</strong> {decision.reviewer_note}</section>}
      {decision.review_state === 'review_required' && <IdentityReviewForm key={decision.decision_id} decision={decision} entities={entities} entityTypes={entityTypes} reviewNote={reviewNote} reviewing={reviewing} setReviewNote={setReviewNote} review={review} />}
    </div>
  );
}

function IdentityReviewForm({ decision, entities, entityTypes, reviewNote, reviewing, setReviewNote, review }: Pick<IdentityDetailProps, 'decision' | 'entities' | 'entityTypes' | 'reviewNote' | 'reviewing' | 'setReviewNote' | 'review'>) {
  const [entityId, setEntityId] = useState(decision.entity_id ?? '');
  const [entityType, setEntityType] = useState(decision.proposed_entity_type);
  const [title, setTitle] = useState(decision.proposed_title);
  const [scope, setScope] = useState<string>(decision.proposed_scope ?? 'independent');
  const [pageState, setPageState] = useState<string>(decision.proposed_page_state ?? 'provisional');
  const [parentEntityId, setParentEntityId] = useState(decision.proposed_parent_entity_id ?? '');
  const contained = scope === 'component' || scope === 'occurrence';
  const noPage = contained || scope === 'context' || scope === 'standalone_event';
  const matchingEntities = entities.filter((entity) => entity.status === 'active' && entity.entity_type === entityType);
  const parentChoices = entities.filter((entity) => entity.status === 'active' && (entity.entity_type === 'project' || entity.entity_type === 'series'));
  const changeScope = (value: typeof scope) => { setScope(value); setPageState(value === 'independent' ? (decision.proposed_page_state === 'materialized' ? 'materialized' : 'provisional') : 'no_page'); if (value !== 'component' && value !== 'occurrence') setParentEntityId(''); if (value === 'standalone_event' || value === 'occurrence') { setEntityType('event'); setEntityId(''); } };
  const approve = () => review('approve', { entity_id: entityId || null, entity_type: entityType, title: title.trim(), scope, page_state: noPage ? 'no_page' : pageState, parent_entity_id: contained ? parentEntityId || null : null });
  return <section className="rounded-xl border border-slate-200 p-4"><p className="text-sm text-slate-600">Choose the authoritative identity shape and page admission. Approval reopens the supporting claims and immediately reruns routing.</p><div className="mt-4 grid gap-3 md:grid-cols-2"><label className="text-xs font-semibold text-slate-700">Canonical identity<select value={entityId} onChange={(event) => setEntityId(event.target.value)} className="mt-1 w-full rounded-lg border-slate-200 text-sm"><option value="">Create a new canonical identity</option>{matchingEntities.map((entity) => <option key={entity.entity_id} value={entity.entity_id}>{entity.title} · {entity.materialization_state}</option>)}</select></label><label className="text-xs font-semibold text-slate-700">Title<input value={title} onChange={(event) => setTitle(event.target.value)} className="mt-1 w-full rounded-lg border-slate-200 text-sm" /></label><label className="text-xs font-semibold text-slate-700">Entity type<select value={entityType} onChange={(event) => { setEntityType(event.target.value); setEntityId(''); }} className="mt-1 w-full rounded-lg border-slate-200 text-sm">{entityTypes.filter((item) => item.discoverable).map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}</select></label><label className="text-xs font-semibold text-slate-700">Identity scope<select value={scope} onChange={(event) => changeScope(event.target.value)} className="mt-1 w-full rounded-lg border-slate-200 text-sm"><option value="independent">Independent identity</option><option value="component">Contained component</option><option value="occurrence">Project/series occurrence</option><option value="standalone_event">Standalone event</option><option value="context">Context only</option></select></label>{!noPage && <label className="text-xs font-semibold text-slate-700">Page admission<select value={pageState} onChange={(event) => setPageState(event.target.value)} className="mt-1 w-full rounded-lg border-slate-200 text-sm"><option value="materialized">Materialize page now</option><option value="provisional">Keep provisional</option></select></label>}{contained && <label className="text-xs font-semibold text-slate-700">Parent Project or Series<select value={parentEntityId} onChange={(event) => setParentEntityId(event.target.value)} className="mt-1 w-full rounded-lg border-slate-200 text-sm"><option value="">Select an exact parent</option>{parentChoices.map((entity) => <option key={entity.entity_id} value={entity.entity_id}>{entity.title}</option>)}</select></label>}</div><label className="mt-4 block text-sm font-bold" htmlFor="identity-review-note">Reviewer note</label><textarea id="identity-review-note" value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} placeholder="Optional rationale for the audit record" className="mt-2 min-h-24 w-full rounded-lg border border-slate-200 p-3 text-sm outline-none focus:ring-2 focus:ring-indigo-500" /><div className="mt-3 flex flex-wrap gap-2"><button disabled={reviewing !== null || !title.trim() || (contained && !parentEntityId)} onClick={() => void approve()} className="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"><ThumbsUp size={16} />{reviewing === 'approve' ? 'Applying and rerouting…' : 'Approve and reroute'}</button><button disabled={reviewing !== null} onClick={() => void review('reject')} className="flex items-center gap-2 rounded-lg border border-rose-200 px-4 py-2 text-sm font-semibold text-rose-700 disabled:opacity-50"><ThumbsDown size={16} />{reviewing === 'reject' ? 'Rejecting and rerouting…' : 'Reject and reroute'}</button></div></section>;
}

interface OrganizationDetailProps {
  proposal: OrganizationProposalArtifact;
  reviewNote: string;
  reviewing: 'approve' | 'reject' | null;
  setReviewNote: (value: string) => void;
  selectClaim: (id: string) => void;
  selectEntity: (id: string) => void;
  review: (decision: 'approve' | 'reject') => Promise<void>;
}

export function OrganizationDetail({ proposal, reviewNote, reviewing, setReviewNote, selectClaim, selectEntity, review }: OrganizationDetailProps) {
  const entityIds = [proposal.source_entity_id, proposal.target_entity_id, proposal.proposed_owner_entity_id].filter((id): id is string => Boolean(id));
  return (
    <div className="mx-auto max-w-4xl space-y-6 p-5 md:p-8">
      <div>
        <div className="flex flex-wrap gap-2"><Badge tone="indigo">{proposal.proposal_type.replaceAll('_', ' ')}</Badge><Badge tone={proposal.status === 'pending' ? 'amber' : proposal.status === 'applied' ? 'green' : proposal.status === 'stale' ? 'red' : 'slate'}>{proposal.status}</Badge><Badge>{percentage(proposal.confidence)}</Badge></div>
        <h2 className="mt-4 text-xl font-bold">Organization decision</h2>
        <div className="mt-2 break-all font-mono text-xs text-slate-400">{proposal.proposal_id} · {formatDate(proposal.created_at)}</div>
      </div>
      <div className="rounded-xl border border-indigo-100 bg-indigo-50/50 p-4 text-sm leading-relaxed text-indigo-950">{proposal.explanation}</div>
      {proposal.claim_id && <button onClick={() => selectClaim(proposal.claim_id!)} className="flex w-full items-center justify-between rounded-lg border border-slate-200 p-3 text-left"><span><strong>Claim</strong><br /><span className="font-mono text-xs text-slate-500">{proposal.claim_id}</span></span><ChevronRight size={15} /></button>}
      {proposal.proposal_type === 'assign_claim' && <section className="rounded-xl border border-slate-200 p-4 text-sm"><div><strong>Proposed owner:</strong> {proposal.proposed_owner_entity_id ?? proposal.proposed_new_entity_title ?? 'Not specified'}</div><div className="mt-2"><strong>Section:</strong> {proposal.proposed_section_key ?? 'Not specified'}</div>{proposal.proposed_new_entity_type && <div className="mt-2"><strong>New entity type:</strong> {proposal.proposed_new_entity_type}</div>}</section>}
      {proposal.proposal_type === 'merge_entities' && <section className="rounded-xl border border-slate-200 p-4 text-sm"><strong>Proposed merge:</strong> {proposal.source_entity_id} → {proposal.target_entity_id}</section>}
      {entityIds.length > 0 && <section><h3 className="mb-2 text-sm font-bold">Affected entities</h3><div className="flex flex-wrap gap-2">{[...new Set(entityIds)].map((id) => <button key={id} onClick={() => selectEntity(id)} className="rounded-md bg-indigo-50 px-3 py-2 font-mono text-xs text-indigo-700">{id}</button>)}</div></section>}
      {proposal.reviewer_note && <section className="rounded-lg bg-slate-50 p-4 text-sm"><strong>Reviewer note:</strong> {proposal.reviewer_note}</section>}
      {proposal.status === 'pending' && <section className="rounded-xl border border-slate-200 p-4"><label className="text-sm font-bold" htmlFor="organization-review-note">Reviewer note</label><textarea id="organization-review-note" value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} placeholder="Optional rationale for the audit record" className="mt-2 min-h-24 w-full rounded-lg border border-slate-200 p-3 text-sm outline-none focus:ring-2 focus:ring-indigo-500" /><div className="mt-3 flex flex-wrap gap-2"><button disabled={reviewing !== null} onClick={() => void review('approve')} className="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"><ThumbsUp size={16} />{reviewing === 'approve' ? 'Applying…' : 'Approve and apply'}</button><button disabled={reviewing !== null} onClick={() => void review('reject')} className="flex items-center gap-2 rounded-lg border border-rose-200 px-4 py-2 text-sm font-semibold text-rose-700 disabled:opacity-50"><ThumbsDown size={16} />{reviewing === 'reject' ? 'Rejecting…' : 'Reject proposal'}</button></div></section>}
    </div>
  );
}
