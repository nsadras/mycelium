export function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded-lg bg-slate-950 p-3 text-xs leading-relaxed text-slate-300">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

export function EmptyState({ children }: { children: string }) {
  return <div className="p-8 text-center text-sm text-slate-400">{children}</div>;
}

export function Badge({ children, tone = 'slate' }: { children: React.ReactNode; tone?: 'slate' | 'green' | 'amber' | 'red' | 'indigo' }) {
  const colors = {
    slate: 'bg-slate-100 text-slate-600',
    green: 'bg-emerald-50 text-emerald-700',
    amber: 'bg-amber-50 text-amber-700',
    red: 'bg-rose-50 text-rose-700',
    indigo: 'bg-indigo-50 text-indigo-700',
  };
  return <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${colors[tone]}`}>{children}</span>;
}
