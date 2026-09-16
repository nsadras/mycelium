import { useEffect, useRef, useState } from 'react';
import api from '../lib/api';

export interface CorrectionPreview {
  status: 'review_required';
  draft_id: string;
  claim_id: string;
  text: string;
  times: {
    time_id: string;
    expression: string;
    target: string;
    role: string;
    options: { reference_id: string; label: string; anchor: string | null; start: string | null; end: string | null }[];
  }[];
}

export default function ClaimCorrectionEditor({ claimIds, onSaved }: {
  claimIds: string[]; onSaved: () => Promise<void>;
}) {
  const idsKey = JSON.stringify(claimIds);
  const [loaded, setLoaded] = useState<{ key: string; texts: Record<string, string> } | null>(null);
  const [selected, setSelected] = useState(claimIds[0] ?? '');
  const [text, setText] = useState('');
  const [preview, setPreview] = useState<CorrectionPreview | null>(null);
  const [choices, setChoices] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  const loading = loaded?.key !== idsKey;

  useEffect(() => {
    const controller = new AbortController();
    const ids = JSON.parse(idsKey) as string[];
    const token = ++generation.current;
    Promise.all(ids.map(async id => {
      const response = await api.get<{ text: string }>(`/memory/artifacts/claims/${encodeURIComponent(id)}`, { signal: controller.signal });
      return [id, response.data.text] as const;
    })).then(entries => {
      if (controller.signal.aborted || generation.current !== token) return;
      const texts = Object.fromEntries(entries);
      setLoaded({ key: idsKey, texts }); setSelected(ids[0]); setText(texts[ids[0]] ?? '');
      setPreview(null); setChoices({}); setError(null); setBusy(false);
    }).catch(() => {
      if (!controller.signal.aborted && generation.current === token) setError('Could not load the statement to correct.');
    });
    return () => { controller.abort(); generation.current += 1; };
  }, [idsKey]);

  const edit = (value: string) => { setText(value); setPreview(null); setChoices({}); setError(null); };
  const save = async (reviewed: boolean) => {
    const token = ++generation.current;
    setBusy(true); setError(null);
    try {
      const response = await api.post<CorrectionPreview | { claim_ids: string[] }>(
        `/memory/claims/${encodeURIComponent(selected)}/correct`,
        { text, ...(reviewed && preview ? { draft_id: preview.draft_id, time_references: choices } : {}) },
      );
      if (generation.current !== token) return;
      if ('status' in response.data && response.data.status === 'review_required') {
        setPreview(response.data); setChoices({});
      } else {
        await onSaved();
      }
    } catch (caught) {
      if (generation.current !== token) return;
      const detail = (caught as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
      if ((caught as { response?: { status?: number } }).response?.status === 409) {
        setPreview(null); setChoices({});
      }
      setError(typeof detail === 'string' ? detail : 'The correction was not completed. You can retry safely.');
    } finally {
      if (generation.current === token) setBusy(false);
    }
  };
  const ready = preview?.times.every(time => Boolean(choices[time.time_id])) ?? false;

  return <div className="space-y-3">
    <label className="block font-semibold" htmlFor={`correction-${selected}`}>Correct the underlying statement</label>
    {claimIds.length > 1 && <select aria-label="Statement to correct" value={selected} disabled={loading || busy}
      onChange={event => { setSelected(event.target.value); edit(loaded?.texts[event.target.value] ?? ''); }}
      className="w-full rounded border-slate-200 text-xs">
      {claimIds.map(id => <option key={id} value={id}>{loaded?.texts[id] ?? 'Loading…'}</option>)}
    </select>}
    <textarea id={`correction-${selected}`} value={loading ? '' : text} disabled={loading || busy}
      onChange={event => edit(event.target.value)} className="w-full rounded border-slate-200 text-sm" rows={3} />
    {preview && <section className="space-y-3 rounded border border-amber-200 bg-amber-50 p-3" aria-label="Review correction dates">
      <h3 className="font-semibold">Review the dates before saving</h3>
      {preview.times.map(time => {
        const option = time.options.find(value => value.reference_id === choices[time.time_id]);
        return <div key={time.time_id}>
          <p className="font-semibold">{time.target}</p>
          <p>Source wording: “{time.expression}” · {time.role.replaceAll('_', ' ')}</p>
          <select aria-label={`Reference date for ${time.target}`} value={choices[time.time_id] ?? ''} disabled={busy}
            onChange={event => setChoices(current => ({ ...current, [time.time_id]: event.target.value }))}
            className="mt-1 w-full rounded border-slate-200 text-xs">
            <option value="" disabled>Choose the reference date…</option>
            {time.options.map(value => <option key={value.reference_id} value={value.reference_id}>
              {value.label} · {value.anchor?.slice(0, 10) ?? 'unknown reference'} → {value.start ?? 'unresolved'}
            </option>)}
          </select>
          {option && <p className="mt-1 font-semibold">Result: {option.start ?? 'Date remains unresolved'}
            {option.end && option.end !== option.start ? ` through ${option.end}` : ''}</p>}
        </div>;
      })}
      <button disabled={busy || !ready} onClick={() => save(true)} className="rounded bg-slate-800 px-3 py-2 font-semibold text-white disabled:opacity-50">
        {busy ? 'Saving…' : 'Save reviewed dates'}
      </button>
      <button disabled={busy} onClick={() => { setPreview(null); setChoices({}); }} className="ml-3 underline">Back to editing</button>
    </section>}
    {!preview && <button disabled={loading || busy || !text.trim()} onClick={() => save(false)}
      className="rounded bg-slate-800 px-3 py-2 font-semibold text-white disabled:opacity-50">
      {busy ? 'Preparing correction…' : 'Save correction'}
    </button>}
    {error && <p role="alert" className="text-red-700">{error}</p>}
  </div>;
}
