import { ChevronRight, ThumbsDown, ThumbsUp } from 'lucide-react';

import type {
  ConsolidatedFactDetail,
  EntityArtifactDetail,
  MemoryClaimArtifact,
  OrganizationProposalArtifact,
} from '../../lib/api';
import { Badge, EmptyState, JsonBlock } from './presentation';
import { formatDate, percentage } from './utils';

interface ClaimDetailProps {
  claim: MemoryClaimArtifact;
  selectSource: (id: string) => void;
  selectFact: (id: string) => void;
  selectReconciliation: (id: string) => void;
}

export function ClaimDetail({ claim, selectSource, selectFact, selectReconciliation }: ClaimDetailProps) {
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
      <section className="grid gap-4 md:grid-cols-2"><div><h3 className="mb-2 text-sm font-bold">Facets</h3><JsonBlock value={claim.facets} /></div><div><h3 className="mb-2 text-sm font-bold">Links</h3><JsonBlock value={claim.links} /></div></section>
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
      <div><div className="flex flex-wrap gap-2"><Badge tone="indigo">{entity.entity_type}</Badge><Badge tone={entity.status === 'active' ? 'green' : 'slate'}>{entity.status}</Badge>{entity.page?.exists && <Badge tone="green">wiki page</Badge>}</div><h2 className="mt-4 text-2xl font-bold">{entity.title}</h2><div className="mt-2 break-all font-mono text-xs text-slate-400">{entity.entity_id} · {entity.slug}</div></div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{counts.map(([label, value]) => <div key={label} className="rounded-lg bg-slate-50 p-3"><div className="text-lg font-bold">{value}</div><div className="text-xs text-slate-500">{label}</div></div>)}</div>
      <section><h3 className="mb-3 text-sm font-bold">Current consolidated facts</h3><div className="space-y-2">{entity.facts.map((fact) => <button key={fact.fact_id} onClick={() => selectFact(fact.fact_id)} className="flex w-full items-center justify-between rounded-lg border border-slate-200 p-3 text-left"><span><strong className="text-sm">{fact.text}</strong><br /><span className="text-xs text-slate-500">{fact.section_key} · {fact.member_claim_ids.length} claims</span></span><ChevronRight size={15} /></button>)}{!entity.facts.length && <EmptyState>No current facts for this entity.</EmptyState>}</div></section>
      <section><h3 className="mb-3 text-sm font-bold">Canonical claim assignments</h3><div className="flex flex-wrap gap-2">{entity.placements.map((placement) => <button key={placement.claim_id} onClick={() => selectClaim(placement.claim_id)} className="rounded-md bg-indigo-50 px-3 py-2 font-mono text-xs text-indigo-700">{placement.claim_id}</button>)}{!entity.placements.length && <span className="text-sm text-slate-500">No claims are assigned to this entity.</span>}</div></section>
      <section><h3 className="mb-2 text-sm font-bold">Identity resolution audit</h3><JsonBlock value={entity.resolution_decisions} /></section>
      <section><h3 className="mb-2 text-sm font-bold">Encounter history</h3><JsonBlock value={entity.encounters} /></section>
    </div>
  );
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
