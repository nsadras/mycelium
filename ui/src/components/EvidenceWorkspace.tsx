import { useMemo, useState } from 'react';
import { BookOpen, ChevronDown, ChevronRight } from 'lucide-react';
import { clsx as cn } from 'clsx';
import type { Message } from '../lib/api';

export default function EvidenceWorkspace({ workspace }: { workspace: NonNullable<Message['memory_workspace']> }) {
  const [open, setOpen] = useState(false);
  const groupedRecords = useMemo(() => {
    const groups = new Map<string, typeof workspace.evidence.records>();
    for (const record of workspace.evidence.records) {
      const subject = record.subject_name || record.subject_entity_id || 'Unassigned';
      groups.set(subject, [...(groups.get(subject) ?? []), record]);
    }
    return Array.from(groups.entries());
  }, [workspace]);

  return (
    <div className="mb-3 border-b border-slate-200 pb-2 text-xs">
      <button
        type="button"
        onClick={() => setOpen(value => !value)}
        className="flex w-full items-center gap-2 rounded-md bg-white px-2 py-1.5 text-left ring-1 ring-slate-200"
        title="Show the evidence accumulated while answering"
      >
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <BookOpen size={13} className="text-violet-500" />
        <span className="font-semibold text-slate-700">Evidence workspace</span>
        <span className="ml-auto text-[10px] text-slate-500">
          {workspace.evidence.records.length} records · {workspace.evidence.sources.length} sources · revision {workspace.revision}
        </span>
      </button>
      {open && (
        <div className="mt-1.5 max-h-96 space-y-3 overflow-auto rounded-md bg-white p-3 ring-1 ring-slate-200">
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-slate-500">
            <span>{workspace.remaining_searches} searches remaining</span>
            <span>{workspace.remaining_evidence_tokens} evidence tokens remaining</span>
            {workspace.last_operation_status === 'failed' && <span className="text-rose-700">Latest memory operation failed</span>}
            {workspace.evidence.more_available && <span>More evidence was available</span>}
          </div>

          {workspace.operations.length > 0 && (
            <section>
              <div className="mb-1 font-semibold uppercase tracking-wide text-slate-400">Operations</div>
              <div className="space-y-1">
                {workspace.operations.map(operation => (
                  <div key={operation.sequence} className="rounded border border-slate-100 px-2 py-1.5">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[10px] text-slate-400">#{operation.sequence}</span>
                      <span className="font-semibold text-slate-700">{operation.tool_name}</span>
                      <span className={cn(
                        "ml-auto rounded px-1.5 py-0.5 text-[10px] font-semibold",
                        operation.status === 'complete' ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"
                      )}>
                        {operation.status}
                      </span>
                    </div>
                    {(operation.query || operation.requested_claim_ids.length > 0) && (
                      <div className="mt-1 text-slate-500">
                        {operation.query || operation.requested_claim_ids.join(', ')}
                      </div>
                    )}
                    {operation.error && <div className="mt-1 text-rose-600">{operation.error}</div>}
                  </div>
                ))}
              </div>
            </section>
          )}

          {groupedRecords.length > 0 && (
            <section>
              <div className="mb-1 font-semibold uppercase tracking-wide text-slate-400">Records</div>
              <div className="space-y-2">
                {groupedRecords.map(([subject, records]) => (
                  <div key={subject} className="rounded border border-slate-100 p-2">
                    <div className="mb-1 font-semibold text-slate-700">{subject}</div>
                    <div className="space-y-1.5">
                      {records.map(record => (
                        <div key={record.record_id}>
                          <div className="text-slate-700">{record.statement}</div>
                          <div className="font-mono text-[10px] text-slate-400">{record.record_type} · {record.record_id} · {record.state}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {workspace.evidence.sources.length > 0 && (
            <section>
              <div className="mb-1 font-semibold uppercase tracking-wide text-slate-400">Inspected sources</div>
              <div className="space-y-2">
                {workspace.evidence.sources.map(source => (
                  <div key={source.source_id} className="rounded border border-slate-100 p-2">
                    <div className="mb-1 flex gap-2 text-[10px] text-slate-400">
                      <span className="font-mono">{source.source_id}</span>
                      <span>{source.conversation_time}</span>
                    </div>
                    <p className={source.status === 'retracted' ? 'text-rose-700' : 'text-slate-500'}>
                      Source status: {source.status}{source.retraction_reason ? ` — ${source.retraction_reason}` : ''}
                    </p>
                    {source.citations.map(citation => <p key={citation.claim_id} className="font-mono text-[10px] text-slate-500">
                      Claim {citation.claim_id} cites {citation.segment_ids.join(', ')}
                    </p>)}
                    <div className="space-y-1">
                      {source.segments.map(segment => (
                        <div key={segment.segment_id} className={cn(
                          "rounded px-1.5 py-1 leading-relaxed",
                          segment.relationship === 'cited' ? "bg-violet-50 text-slate-800" : "text-slate-500"
                        )}>
                          {segment.speaker && <span className="font-semibold">{segment.speaker}: </span>}
                          {segment.content}
                          <span className="ml-2 font-mono text-[10px] text-slate-400">{segment.segment_id} · {segment.relationship}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
