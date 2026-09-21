import { useEffect, useState } from 'react';
import api, { type EntityRecord, type EntityResolutionDecisionArtifact, type EntityTypeOntology, type IdentityReviewEdits, type MemoryClaimArtifact } from '../../lib/api';

interface Props {
  decision: EntityResolutionDecisionArtifact;
  entities: EntityRecord[];
  entityTypes: EntityTypeOntology[];
  reviewNote: string;
  reviewing: 'approve' | 'reject' | null;
  setReviewNote: (value: string) => void;
  review: (action: 'approve' | 'reject', edits?: IdentityReviewEdits) => Promise<void>;
}

export default function IdentityReviewForm({ decision, entities, entityTypes, reviewNote, reviewing, setReviewNote, review }: Props) {
  const [entityId, setEntityId] = useState(decision.entity_id ?? '');
  const [title, setTitle] = useState(decision.proposed_title);
  const [entityType, setEntityType] = useState(decision.proposed_entity_type === 'you' ? 'person' : decision.proposed_entity_type);
  const [allowPage, setAllowPage] = useState(decision.proposed_page_state !== 'no_page');
  const [claims, setClaims] = useState<MemoryClaimArtifact[] | null>(null);
  const [texts, setTexts] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const idsKey = JSON.stringify(decision.supporting_claim_ids);
  useEffect(() => {
    let active = true;
    const ids: string[] = JSON.parse(idsKey);
    void Promise.all(ids.map(id => api.get<MemoryClaimArtifact>(`/memory/artifacts/claims/${encodeURIComponent(id)}`)))
      .then(results => {
        if (!active) return;
        const current = results.map(r => r.data).filter(c => c.status === 'active');
        setClaims(current);
        setTexts(Object.fromEntries(current.map(c => [c.claim_id, c.text])));
      }).catch(() => { if (active) setError('Could not load the affected statements. Reopen this identity to try again.'); });
    return () => { active = false; };
  }, [idsKey]);
  const choices = entities.filter(e => e.status === 'active' && (e.entity_type === entityType || (entityType === 'person' && e.entity_type === 'you')));
  const selected = choices.find(e => e.entity_id === entityId);
  const apply = () => review('approve', {
    entity_id: entityId,
    entity_type: selected?.entity_type ?? entityType,
    ...(entityId ? {} : { title: title.trim() }),
    scope: allowPage ? 'independent' : 'context',
    page_state: allowPage ? 'provisional' : 'no_page',
    claim_texts: Object.fromEntries((claims ?? []).filter(c => texts[c.claim_id] !== c.text).map(c => [c.claim_id, texts[c.claim_id]])),
  });
  return <section className="rounded-xl border border-slate-200 p-4">
    <h3 className="font-bold">Correct identity</h3>
    <p className="mt-2 text-sm text-slate-600">Choose who these statements refer to. This updates the selected evidence and any speaker binding established by this decision.</p>
    <label className="mt-4 block text-sm">Identity
      <select aria-label="Identity" value={entityId} onChange={e => setEntityId(e.target.value)} className="mt-1 w-full rounded-lg border-slate-200 text-sm">
        <option value="">Create a distinct identity</option>
        {choices.map(e => <option key={e.entity_id} value={e.entity_id}>{e.title}</option>)}
      </select>
    </label>
    {!entityId && <div className="mt-3 grid gap-3 md:grid-cols-2">
      <label className="text-sm">Name<input aria-label="Name" value={title} onChange={e => setTitle(e.target.value)} className="mt-1 w-full rounded-lg border-slate-200" /></label>
      <label className="text-sm">Type<select aria-label="Type" value={entityType} onChange={e => setEntityType(e.target.value as typeof entityType)} className="mt-1 w-full rounded-lg border-slate-200">
        {entityTypes.filter(t => t.discoverable).map(t => <option key={t.key} value={t.key}>{t.label}</option>)}
      </select></label>
    </div>}
    <label className="mt-4 flex gap-2 text-sm"><input type="checkbox" checked={allowPage} onChange={e => setAllowPage(e.target.checked)} />Allow this evidence on this identity's page</label>
    <p className="mt-3 text-xs text-slate-600">Update names or references in the statements below. Dates and other facts retain their existing meaning; use Correct memory for other changes.</p>
    {claims === null && !error && <p className="mt-3 text-sm">Loading affected statements…</p>}
    {claims?.map((claim, index) => <label key={claim.claim_id} className="mt-3 block text-sm">Statement {index + 1}
      <textarea aria-label={`Statement ${index + 1}`} value={texts[claim.claim_id] ?? claim.text} onChange={e => setTexts(old => ({ ...old, [claim.claim_id]: e.target.value }))} className="mt-1 min-h-24 w-full rounded-lg border-slate-200" />
    </label>)}
    <label className="mt-3 block text-sm">Note (optional)<textarea aria-label="Review note" value={reviewNote} onChange={e => setReviewNote(e.target.value)} className="mt-1 w-full rounded-lg border-slate-200" /></label>
    {error && <p role="alert" className="mt-3 text-sm text-rose-700">{error}</p>}
    <button disabled={reviewing !== null || claims === null || !!error || (!entityId && !title.trim()) || (claims ?? []).some(c => !texts[c.claim_id]?.trim())}
      onClick={() => void apply()} className="mt-3 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
      {reviewing ? 'Saving…' : 'Save identity correction'}
    </button>
  </section>;
}
