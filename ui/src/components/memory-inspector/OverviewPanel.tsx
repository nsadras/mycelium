import { AlertTriangle, CheckCircle2 } from 'lucide-react';

import type { ArtifactOverview } from '../../lib/api';
import { Badge } from './presentation';
import { formatDate, humanize, percentage } from './utils';

export function OverviewPanel({ overview }: { overview: ArtifactOverview }) {
  return (
        <div className="flex-1 overflow-y-auto p-4 md:p-8">
          <div className="mx-auto max-w-6xl space-y-6">
            <section className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-6">
              {[
                ['Sources', overview.coverage.sources],
                ['Episodes', overview.coverage.episodes],
                ['Claims', overview.coverage.claims],
                ['Facts', overview.lifecycle.consolidated_facts],
                ['Entities', overview.lifecycle.entities],
                ['Wiki pages', overview.lifecycle.wiki_pages],
                ['Dream runs', overview.dream_audit.runs],
                ['Actionable reviews', overview.review_inbox.identity_decisions + overview.review_inbox.organization_proposals + overview.review_inbox.reconsolidation_proposals],
                ['Identity reviews', overview.review_inbox.identity_decisions],
                ['Provisional identities', overview.review_inbox.provisional_entities],
                ['Suppressed', overview.coverage.suppressed_claims],
                ['Segments', overview.coverage.segments],
                ['Reconciliation reviews', overview.reconsolidation_proposals.pending ?? 0],
                ['Organization reviews', overview.organization_proposals.pending ?? 0],
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
                    ['Source-only segments', overview.coverage.source_only_segments, overview.coverage.segments ? overview.coverage.source_only_segments / overview.coverage.segments : 0],
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
  );
}
