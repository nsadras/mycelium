import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import api, { type EngramMeeting } from '../lib/api';
import Engram from './Engram';

vi.mock('../lib/api', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() }, engramAudioUrl: vi.fn() }));

function meeting(id: string, status: EngramMeeting['status'] = 'reviewing'): EngramMeeting {
  return { id, title: `Meeting ${id}`, status, created_at: '2026-01-01', started_at: '2026-01-01', ended_at: null,
    speaker_names: {}, segment_count: 1, warnings: [], admission_started_at: null,
    segments: [{ id: id === 'A' ? 1 : 2, meeting_id: id, segment_index: 0, start_seconds: 0, end_seconds: 1,
      text: `Transcript ${id}`, speaker: 'SPEAKER_00', status: 'diarized', created_at: '2026-01-01' }] };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

let a: EngramMeeting;
let b: EngramMeeting;
beforeEach(() => {
  vi.resetAllMocks();
  a = meeting('A'); b = meeting('B');
  vi.mocked(api.get).mockImplementation(async url => ({ data: url === '/engram/meetings' ? [a, b] : url.endsWith('/A') ? a : b }));
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  vi.spyOn(console, 'error').mockImplementation(() => {});
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

async function open() {
  const status = vi.fn();
  render(<Engram setAssistantStatus={status} />);
  await screen.findByRole('heading', { name: 'Meeting A' });
  return { user: userEvent.setup(), status };
}

it('hides the previous transcript immediately and ignores obsolete detail loads', async () => {
  const { user } = await open();
  const response = deferred<{ data: EngramMeeting }>();
  vi.mocked(api.get).mockImplementationOnce(() => response.promise);
  await user.click(screen.getByRole('button', { name: /Meeting B/ }));
  expect(screen.queryByText('Transcript A')).toBeNull();
  await user.click(screen.getByRole('button', { name: /Meeting A/ }));
  await screen.findByRole('heading', { name: 'Meeting A' });
  await act(async () => { response.resolve({ data: b }); });
  expect(screen.queryByRole('heading', { name: 'Meeting B' })).toBeNull();
  expect(screen.getByText('Transcript A')).toBeTruthy();
});

it('ignores a speaker-save response after switching away and back', async () => {
  const { user } = await open();
  const saved = deferred<{ data: EngramMeeting }>();
  vi.mocked(api.put).mockImplementationOnce(() => saved.promise);
  await user.click(screen.getByTitle('Save speaker names'));
  await user.click(screen.getByRole('button', { name: /Meeting B/ }));
  await screen.findByRole('heading', { name: 'Meeting B' });
  const refreshed = structuredClone(a);
  refreshed.segments![0].text = 'New A transcript';
  vi.mocked(api.get).mockResolvedValueOnce({ data: refreshed });
  await user.click(screen.getByRole('button', { name: /Meeting A/ }));
  await screen.findByText('New A transcript');
  await act(async () => { saved.resolve({ data: a }); });
  expect(screen.getByText('New A transcript')).toBeTruthy();
  expect(screen.queryByText('Transcript A')).toBeNull();
  expect((screen.getByTitle('Save speaker names') as HTMLButtonElement).disabled).toBe(false);
});

it.each([false, true])('does not apply a delayed process response to another meeting (failure=%s)', async failure => {
  a.status = 'ready';
  const { user, status } = await open();
  const processed = deferred<{ data: EngramMeeting }>();
  vi.mocked(api.post).mockImplementationOnce(() => processed.promise);
  await user.click(screen.getByRole('button', { name: 'Process' }));
  await user.click(screen.getByRole('button', { name: /Meeting B/ }));
  await screen.findByRole('heading', { name: 'Meeting B' });
  status.mockClear();
  await act(async () => { if (failure) processed.reject(new Error('Late failure')); else processed.resolve({ data: { ...a, status: 'processing' } }); });
  expect(screen.getByRole('heading', { name: 'Meeting B' })).toBeTruthy();
  expect(screen.getByText('Transcript B')).toBeTruthy();
  expect(status).not.toHaveBeenCalled();
  expect(screen.queryByRole('alert')).toBeNull();
});

it('stops the finalize sequence when selection changes while speaker names save', async () => {
  const { user } = await open();
  const names = deferred<{ data: EngramMeeting }>();
  vi.mocked(api.put).mockImplementationOnce(() => names.promise);
  await user.click(screen.getByRole('button', { name: 'Finalize' }));
  await user.click(screen.getByRole('button', { name: /Meeting B/ }));
  await screen.findByRole('heading', { name: 'Meeting B' });
  await act(async () => { names.resolve({ data: a }); });
  expect(api.post).not.toHaveBeenCalled();
  expect((screen.getByRole('button', { name: 'Finalize' }) as HTMLButtonElement).disabled).toBe(false);
});

it('preserves the current selection after a delayed delete of another meeting', async () => {
  const { user, status } = await open();
  const deleted = deferred<{ data: { deleted: boolean } }>();
  vi.mocked(api.delete).mockImplementationOnce(() => deleted.promise);
  await user.click(screen.getByRole('button', { name: 'Delete' }));
  await user.click(screen.getByRole('button', { name: /Meeting B/ }));
  await screen.findByRole('heading', { name: 'Meeting B' });
  status.mockClear();
  await act(async () => { deleted.resolve({ data: { deleted: true } }); });
  expect(screen.getByRole('heading', { name: 'Meeting B' })).toBeTruthy();
  expect(screen.queryByRole('button', { name: /Meeting A/ })).toBeNull();
  expect(status).not.toHaveBeenCalled();
});

it('shows durable warning history and retries frozen admission without editing speakers', async () => {
  a.admission_started_at = '2026-01-01T12:00:00';
  a.warnings = [{ id: 'warning', stage: 'diarization', message: 'Device unavailable', created_at: '2026-01-01', resolved_at: null }];
  const { user } = await open();
  expect(screen.getByText('diarization: Device unavailable')).toBeTruthy();
  expect((screen.getByTitle('Save speaker names') as HTMLButtonElement).disabled).toBe(true);
  expect(screen.queryByRole('button', { name: 'Retry speaker detection' })).toBeNull();
  vi.mocked(api.post).mockResolvedValueOnce({ data: { ...a, status: 'completed', summary: { summary: 'Done', decisions: [], action_items: [], open_questions: [] } } });
  await user.click(screen.getByRole('button', { name: 'Finalize' }));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith('/engram/meetings/A/finalize'));
  expect(api.put).not.toHaveBeenCalled();
});
