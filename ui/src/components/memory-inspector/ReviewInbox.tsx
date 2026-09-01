import { ChevronRight } from 'lucide-react';

import type {
  EntityRecord,
  EntityResolutionDecisionArtifact,
  IdentityMaturityAssessmentArtifact,
  OrganizationProposalArtifact,
  ReconsolidationProposalArtifact,
} from '../../lib/api';
import { Badge, EmptyState } from './presentation';
import { humanize } from './utils';

interface ReviewInboxProps {
  identities: EntityResolutionDecisionArtifact[];
  organizations: OrganizationProposalArtifact[];
  reconciliations: ReconsolidationProposalArtifact[];
  provisionalEntities: EntityRecord[];
  maturityAssessments: IdentityMaturityAssessmentArtifact[];
  selectIdentity: (id: string) => void;
  selectOrganization: (id: string) => void;
  selectReconciliation: (id: string) => void;
  selectEntity: (id: string) => void;
  selectDreamRun: (id: string) => void;
}

function ReviewCard({ title, detail, badge, onClick }: { title: string; detail: string; badge: string; onClick: () => void }) {
  return <button onClick={onClick} className="flex w-full items-start justify-between gap-4 rounded-xl border border-amber-200 bg-amber-50/50 p-4 text-left hover:bg-amber-50"><span><span className="font-semibold text-slate-900">{title}</span><span className="mt-1 block text-xs leading-relaxed text-slate-600">{detail}</span></span><span className="flex shrink-0 items-center gap-2"><Badge tone="amber">{badge}</Badge><ChevronRight size={15} className="text-slate-400" /></span></button>;
}

export function ReviewInbox({ identities, organizations, reconciliations, provisionalEntities, maturityAssessments, selectIdentity, selectOrganization, selectReconciliation, selectEntity, selectDreamRun }: ReviewInboxProps) {
  const actionableCount = identities.length + organizations.length + reconciliations.length;
  return <div className="flex-1 overflow-y-auto p-4 md:p-8"><div className="mx-auto max-w-5xl space-y-8"><header><div className="flex flex-wrap items-center gap-2"><h2 className="text-2xl font-bold">Review inbox</h2><Badge tone={actionableCount ? 'amber' : 'green'}>{actionableCount} actionable</Badge></div><p className="mt-2 text-sm text-slate-600">Every pending user decision in one place. Provisional identities and maturity evidence are shown separately because they are waiting for evidence, not approval.</p></header>
    <section><h3 className="mb-3 text-sm font-bold uppercase tracking-wide text-slate-500">Identity decisions · {identities.length}</h3><div className="space-y-2">{identities.map((item) => <ReviewCard key={item.decision_id} title={item.proposed_title} detail={`${item.reason} · proposed ${item.proposed_entity_type} / ${humanize(item.proposed_scope ?? 'unknown scope')} / ${humanize(item.proposed_page_state ?? 'unknown page state')}`} badge="Identity" onClick={() => selectIdentity(item.decision_id)} />)}{!identities.length && <EmptyState>No identity decisions require review.</EmptyState>}</div></section>
    <section><h3 className="mb-3 text-sm font-bold uppercase tracking-wide text-slate-500">Truth changes · {reconciliations.length}</h3><div className="space-y-2">{reconciliations.map((item) => <ReviewCard key={item.proposal_id} title={humanize(item.proposed_relation)} detail={item.explanation} badge="Claim conflict" onClick={() => selectReconciliation(item.proposal_id)} />)}{!reconciliations.length && <EmptyState>No truth-change proposals require review.</EmptyState>}</div></section>
    <section><h3 className="mb-3 text-sm font-bold uppercase tracking-wide text-slate-500">Organization · {organizations.length}</h3><div className="space-y-2">{organizations.map((item) => <ReviewCard key={item.proposal_id} title={humanize(item.proposal_type)} detail={item.explanation} badge="Organization" onClick={() => selectOrganization(item.proposal_id)} />)}{!organizations.length && <EmptyState>No organization proposals require review.</EmptyState>}</div></section>
    <section><h3 className="mb-3 text-sm font-bold uppercase tracking-wide text-slate-500">Provisional identities · {provisionalEntities.length}</h3><div className="grid gap-2 md:grid-cols-2">{provisionalEntities.map((entity) => <button key={entity.entity_id} onClick={() => selectEntity(entity.entity_id)} className="rounded-xl border border-slate-200 p-4 text-left hover:bg-slate-50"><div className="flex items-center justify-between"><span className="font-semibold">{entity.title}</span><Badge>Waiting for evidence</Badge></div><div className="mt-1 text-xs text-slate-500">{entity.entity_type} · {entity.entity_id}</div></button>)}{!provisionalEntities.length && <EmptyState>No provisional identities.</EmptyState>}</div></section>
    <section><h3 className="mb-3 text-sm font-bold uppercase tracking-wide text-slate-500">Maturity evidence requiring review · {maturityAssessments.length}</h3><div className="space-y-2">{maturityAssessments.map((item) => <button key={item.assessment_id} onClick={() => selectDreamRun(item.dream_run_id)} className="w-full rounded-xl border border-slate-200 p-4 text-left hover:bg-slate-50"><div className="flex flex-wrap items-center gap-2"><span className="font-semibold">{item.proposed_title}</span><Badge tone="amber">{humanize(item.effective_admission)}</Badge><Badge>{item.verifier_verdict}</Badge></div><p className="mt-2 text-xs leading-relaxed text-slate-600">Proposal: {item.proposal_reason}</p><p className="mt-1 text-xs leading-relaxed text-slate-500">Verifier: {item.verifier_reason}</p></button>)}{!maturityAssessments.length && <EmptyState>No maturity assessments require review.</EmptyState>}</div></section>
  </div></div>;
}
