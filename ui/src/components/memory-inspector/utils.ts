export function formatDate(value?: string | null) {
  if (!value) return 'Unknown';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function percentage(value: number) {
  return `${Math.round(value * 100)}%`;
}

export function humanize(value: string) {
  return value.replaceAll('_', ' ');
}
