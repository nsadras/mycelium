import { useState } from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import api, { type Message } from '../lib/api';
import Chat from './Chat';

vi.mock('../lib/api', () => ({ default: { get: vi.fn(), post: vi.fn() } }));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const message = (content: string): Message => ({ role: 'assistant', content, timestamp: '2026-01-01T12:00:00Z' });
const histories: Record<string, Message[]> = {};
beforeEach(() => {
  vi.resetAllMocks();
  histories.A = [message('History A')]; histories.B = [message('History B')];
  vi.mocked(api.get).mockImplementation(async url => ({ data: { transcript: histories[url.split('/').at(-1)!] } }));
  vi.spyOn(console, 'error').mockImplementation(() => {});
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function setup() {
  const status = vi.fn();
  function Harness() {
    const [selected, select] = useState('A');
    return <Chat sessions={[{ id: 'A', query: 'Session A' }, { id: 'B', query: 'Session B' }]}
      selectedId={selected} onSelect={select} onCreate={vi.fn()} onRename={vi.fn()} setAssistantStatus={status} />;
  }
  return { ...render(<Harness />), status, user: userEvent.setup() };
}

it('preserves per-session drafts when history fails and hides the previous transcript', async () => {
  const { user } = setup();
  await screen.findByText('History A');
  await user.type(screen.getByRole('textbox'), 'Draft A');
  const loading = deferred<{ data: { transcript: Message[] } }>();
  vi.mocked(api.get).mockImplementationOnce(() => loading.promise);
  await user.click(screen.getByRole('button', { name: 'Session B' }));
  expect(screen.queryByText('History A')).toBeNull();
  expect((screen.getByRole('textbox') as HTMLInputElement).value).toBe('');
  await user.type(screen.getByRole('textbox'), 'Draft B');
  await act(async () => { loading.reject(new Error('Unavailable')); });
  expect((screen.getByRole('textbox') as HTMLInputElement).value).toBe('Draft B');
  expect((screen.getByRole('button', { name: 'Send message' }) as HTMLButtonElement).disabled).toBe(true);
  await user.click(screen.getByRole('button', { name: 'Retry history' }));
  await screen.findByText('History B');
  expect((screen.getByRole('textbox') as HTMLInputElement).value).toBe('Draft B');
  await user.click(screen.getByRole('button', { name: 'Session A' }));
  await screen.findByText('History A');
  expect((screen.getByRole('textbox') as HTMLInputElement).value).toBe('Draft A');
});

it('ignores a delayed history response for another session', async () => {
  const loading = deferred<{ data: { transcript: Message[] } }>();
  vi.mocked(api.get).mockImplementationOnce(() => loading.promise);
  const { user, status } = setup();
  await user.click(screen.getByRole('button', { name: 'Session B' }));
  await screen.findByText('History B');
  status.mockClear();
  await act(async () => { loading.resolve({ data: { transcript: histories.A } }); });
  expect(screen.queryByText('History A')).toBeNull();
  expect(status).not.toHaveBeenCalled();
});

it('keeps a newer session request pending when an older request fails', async () => {
  const { user, status } = setup();
  await screen.findByText('History A');
  const first = deferred<{ data: object }>();
  const second = deferred<{ data: object }>();
  vi.mocked(api.post).mockImplementationOnce(() => first.promise).mockImplementationOnce(() => second.promise);
  await user.type(screen.getByRole('textbox'), 'Question A');
  await user.click(screen.getByRole('button', { name: 'Send message' }));
  await user.click(screen.getByRole('button', { name: 'Session B' }));
  await screen.findByText('History B');
  await user.type(screen.getByRole('textbox'), 'Question B');
  await user.click(screen.getByRole('button', { name: 'Send message' }));
  status.mockClear();
  await act(async () => { first.reject(new Error('Failed A')); });
  expect((screen.getByRole('textbox') as HTMLInputElement).disabled).toBe(true);
  expect(status).not.toHaveBeenCalled();
  expect(screen.queryByRole('alert')).toBeNull();
  await act(async () => { second.resolve({ data: { response: 'Reply B', user_timestamp: '2026-01-02', assistant_timestamp: '2026-01-02' } }); });
  await screen.findByText('Reply B');
  await user.click(screen.getByRole('button', { name: 'Session A' }));
  await screen.findByText('History A');
  expect((screen.getByRole('textbox') as HTMLInputElement).value).toBe('Question A');
});

it('removes only the failed optimistic message and restores its draft', async () => {
  histories.A = [{ role: 'user', content: 'Earlier saved question', timestamp: '2026-01-01T12:00:00.000Z' }];
  vi.spyOn(Date.prototype, 'toISOString').mockReturnValue('2026-01-01T12:00:00.000Z');
  const { user } = setup();
  await screen.findByText('Earlier saved question');
  vi.mocked(api.post).mockRejectedValueOnce(new Error('Offline'));
  await user.type(screen.getByRole('textbox'), 'Failed question');
  await user.click(screen.getByRole('button', { name: 'Send message' }));
  await screen.findByRole('alert');
  expect(screen.getByText('Earlier saved question')).toBeTruthy();
  expect(screen.queryByText('Failed question')).toBeNull();
  expect((screen.getByRole('textbox') as HTMLInputElement).value).toBe('Failed question');
});

it('reloads canonical history after a request finishes across an A-B-A switch', async () => {
  const { user } = setup();
  await screen.findByText('History A');
  const reply = deferred<{ data: object }>();
  vi.mocked(api.post).mockImplementationOnce(() => reply.promise);
  await user.type(screen.getByRole('textbox'), 'Question A');
  await user.click(screen.getByRole('button', { name: 'Send message' }));
  await user.click(screen.getByRole('button', { name: 'Session B' }));
  await screen.findByText('History B');
  await user.click(screen.getByRole('button', { name: 'Session A' }));
  await screen.findByText('History A');
  histories.A = [message('Latest canonical history')];
  await act(async () => { reply.resolve({ data: { response: 'Obsolete response body' } }); });
  await screen.findByText('Latest canonical history');
  expect(screen.queryByText('Obsolete response body')).toBeNull();
  await waitFor(() => expect((screen.getByRole('textbox') as HTMLInputElement).disabled).toBe(false));
});

it('ignores a failed response after unmounting', async () => {
  const { user, status, unmount } = setup();
  await screen.findByText('History A');
  const reply = deferred<{ data: object }>();
  vi.mocked(api.post).mockImplementationOnce(() => reply.promise);
  await user.type(screen.getByRole('textbox'), 'A request');
  await user.click(screen.getByRole('button', { name: 'Send message' }));
  unmount(); status.mockClear();
  await act(async () => { reply.reject(new Error('Late failure')); });
  expect(status).not.toHaveBeenCalled();
});
