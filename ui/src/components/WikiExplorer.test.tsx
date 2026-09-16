import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import api, { type EntityRecord, type MemoryOntology, type WikiPage } from '../lib/api';
import WikiExplorer from './WikiExplorer';

vi.mock('../lib/api', () => ({ default: { get: vi.fn(), patch: vi.fn(), post: vi.fn() } }));

const page = (id: string): WikiPage => ({ slug: id, title: `Page ${id}`, entity_id: id, entity_status: 'active', page_type: 'person', tags: [], aliases: [], version: 1, content: `Content ${id}` });
const entity = (id: string): EntityRecord => ({ entity_id: id, title: `Page ${id}`, slug: id, entity_type: 'person', status: 'active', materialization_state: 'materialized', aliases: [], created_at: '2026-01-01', updated_at: '2026-01-01' });
const ontology: MemoryOntology = { claim_types: [], entity_types: [{ key: 'person', label: 'Person', plural_label: 'People', description: 'A person', discoverable: true, sections: [], default_sections: {} }] };

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.get).mockImplementation(async url => {
    if (url === '/memory/wiki') return { data: [page('A'), page('B')] };
    if (url === '/memory/artifacts/entities') return { data: [entity('A'), entity('B')] };
    if (url === '/memory/ontology') return { data: ontology };
    if (url.startsWith('/memory/wiki/')) return { data: page(url.split('/').at(-1)!) };
    return { data: [] };
  });
});
afterEach(cleanup);

async function setup() {
  render(<WikiExplorer />);
  await screen.findByRole('button', { name: /Page A/ });
  return userEvent.setup();
}

it('hides old page content during navigation and ignores a delayed response', async () => {
  const user = await setup();
  await user.click(screen.getByRole('button', { name: /Page A/ }));
  await screen.findByText('Content A');
  const response = deferred<{ data: WikiPage }>();
  vi.mocked(api.get).mockImplementationOnce(() => response.promise);
  await user.click(screen.getByRole('button', { name: /Page B/ }));
  expect(screen.queryByText('Content A')).toBeNull();
  expect(screen.getByText('Loading wiki page…')).toBeTruthy();
  await user.click(screen.getByRole('button', { name: /Page A/ }));
  await screen.findByText('Content A');
  await act(async () => { response.resolve({ data: page('B') }); });
  expect(screen.queryByText('Content B')).toBeNull();
  expect(screen.getByRole('heading', { name: 'Page A' })).toBeTruthy();
});

it('shows load failures and retries when the same page is selected again', async () => {
  const user = await setup();
  vi.mocked(api.get).mockRejectedValueOnce(new Error('Unavailable'));
  await user.click(screen.getByRole('button', { name: /Page A/ }));
  await screen.findByRole('alert');
  expect(screen.queryByText('Content A')).toBeNull();
  await user.click(screen.getByRole('button', { name: /Page A/ }));
  await screen.findByText('Content A');
  expect(screen.queryByRole('alert')).toBeNull();
});

it('does not navigate or close another page editor after an older edit completes', async () => {
  const user = await setup();
  await user.click(screen.getByRole('button', { name: /Page A/ }));
  await screen.findByText('Content A');
  await user.click(screen.getByRole('button', { name: 'Curate' }));
  const mutation = deferred<{ data: object }>();
  vi.mocked(api.patch).mockImplementationOnce(() => mutation.promise);
  await user.click(screen.getByRole('button', { name: 'Save identity' }));
  await user.click(screen.getByRole('button', { name: /Page B/ }));
  await screen.findByText('Content B');
  await user.click(screen.getByRole('button', { name: 'Curate' }));
  await user.clear(screen.getByPlaceholderText('Title'));
  await user.type(screen.getByPlaceholderText('Title'), 'Current B draft');
  await act(async () => { mutation.resolve({ data: {} }); });
  expect(screen.getByRole('heading', { name: 'Page B' })).toBeTruthy();
  expect((screen.getByPlaceholderText('Title') as HTMLInputElement).value).toBe('Current B draft');
});

it('rejects an old mutation refresh after navigating away and back to its page', async () => {
  const user = await setup();
  await user.click(screen.getByRole('button', { name: /Page A/ }));
  await screen.findByText('Content A');
  await user.click(screen.getByRole('button', { name: 'Curate' }));
  await user.clear(screen.getByPlaceholderText('Slug'));
  await user.type(screen.getByPlaceholderText('Slug'), 'renamed');
  const mutation = deferred<{ data: object }>();
  vi.mocked(api.patch).mockImplementationOnce(() => mutation.promise);
  await user.click(screen.getByRole('button', { name: 'Save identity' }));
  await user.click(screen.getByRole('button', { name: /Page B/ }));
  await screen.findByText('Content B');
  await user.click(screen.getByRole('button', { name: /Page A/ }));
  await screen.findByText('Content A');
  await act(async () => { mutation.resolve({ data: {} }); });
  expect(screen.getByRole('heading', { name: 'Page A' })).toBeTruthy();
  expect(vi.mocked(api.get).mock.calls.some(([url]) => url === '/memory/wiki/renamed')).toBe(false);
});
