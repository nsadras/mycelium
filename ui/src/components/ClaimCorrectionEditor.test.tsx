import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import api from '../lib/api';
import ClaimCorrectionEditor, { type CorrectionPreview } from './ClaimCorrectionEditor';

vi.mock('../lib/api', () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const preview: CorrectionPreview = {
  status: 'review_required', draft_id: 'draft-1', claim_id: 'claim-1',
  text: 'Deliver in two days if payment arrives tomorrow.',
  times: [
    { time_id: '0', expression: 'in two days', target: 'Delivery', role: 'event_time',
      options: [{ reference_id: 'T001', label: 'Original delivery', anchor: '2026-06-10', start: '2026-06-12', end: '2026-06-12' }] },
    { time_id: '1', expression: 'tomorrow', target: 'Payment', role: 'condition_time',
      options: [{ reference_id: 'T002', label: 'Original payment', anchor: '2026-06-10', start: '2026-06-11', end: '2026-06-11' }] },
  ],
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.get).mockResolvedValue({ data: { text: preview.text } });
});
afterEach(cleanup);

async function openPreview() {
  const user = userEvent.setup();
  const onSaved = vi.fn(async () => {});
  vi.mocked(api.post).mockResolvedValueOnce({ data: preview });
  render(<ClaimCorrectionEditor claimIds={['claim-1']} onSaved={onSaved} />);
  await screen.findByDisplayValue(preview.text);
  await user.click(screen.getByRole('button', { name: 'Save correction' }));
  await screen.findByRole('region', { name: 'Review correction dates' });
  return { user, onSaved };
}

describe('relative-date correction review', () => {
  it('requires every date choice and sends the exact reviewed draft', async () => {
    const { user, onSaved } = await openPreview();
    const save = screen.getByRole('button', { name: 'Save reviewed dates' }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    expect(onSaved).not.toHaveBeenCalled();
    await user.selectOptions(screen.getByLabelText('Reference date for Delivery'), 'T001');
    expect(save.disabled).toBe(true);
    expect(screen.getByText('Result: 2026-06-12')).toBeTruthy();
    await user.selectOptions(screen.getByLabelText('Reference date for Payment'), 'T002');
    vi.mocked(api.post).mockResolvedValueOnce({ data: { claim_ids: ['replacement'] } });
    await user.click(save);
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
    expect(api.post).toHaveBeenLastCalledWith('/memory/claims/claim-1/correct', {
      text: preview.text, draft_id: 'draft-1', time_references: { '0': 'T001', '1': 'T002' },
    });
  });

  it('invalidates the preview when replacement text changes', async () => {
    const { user } = await openPreview();
    await user.clear(screen.getByRole('textbox'));
    await user.type(screen.getByRole('textbox'), 'A different replacement.');
    expect(screen.queryByRole('region', { name: 'Review correction dates' })).toBeNull();
    vi.mocked(api.post).mockResolvedValueOnce({ data: { claim_ids: ['replacement'] } });
    await user.click(screen.getByRole('button', { name: 'Save correction' }));
    expect(api.post).toHaveBeenLastCalledWith('/memory/claims/claim-1/correct', { text: 'A different replacement.' });
  });

  it('preserves the reviewed draft on a retryable failure', async () => {
    const { user, onSaved } = await openPreview();
    await user.selectOptions(screen.getByLabelText('Reference date for Delivery'), 'T001');
    await user.selectOptions(screen.getByLabelText('Reference date for Payment'), 'T002');
    vi.mocked(api.post).mockRejectedValueOnce(new Error('connection lost'));
    await user.click(screen.getByRole('button', { name: 'Save reviewed dates' }));
    await screen.findByRole('alert');
    expect((screen.getByLabelText('Reference date for Delivery') as HTMLSelectElement).value).toBe('T001');
    expect(onSaved).not.toHaveBeenCalled();
    vi.mocked(api.post).mockResolvedValueOnce({ data: { claim_ids: ['replacement'] } });
    await user.click(screen.getByRole('button', { name: 'Save reviewed dates' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
  });

  it('discards a stale preview while retaining the replacement draft', async () => {
    const { user } = await openPreview();
    await user.selectOptions(screen.getByLabelText('Reference date for Delivery'), 'T001');
    await user.selectOptions(screen.getByLabelText('Reference date for Payment'), 'T002');
    vi.mocked(api.post).mockRejectedValueOnce({ response: { status: 409, data: { detail: 'Memory changed during review.' } } });
    await user.click(screen.getByRole('button', { name: 'Save reviewed dates' }));
    await screen.findByText('Memory changed during review.');
    expect(screen.queryByRole('region', { name: 'Review correction dates' })).toBeNull();
    expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe(preview.text);
  });

  it('ignores a delayed load for another claim', async () => {
    let oldResponse!: (value: { data: { text: string } }) => void;
    vi.mocked(api.get).mockImplementationOnce(() => new Promise(resolve => { oldResponse = resolve; }));
    const onSaved = vi.fn(async () => {});
    const { rerender } = render(<ClaimCorrectionEditor claimIds={['old']} onSaved={onSaved} />);
    vi.mocked(api.get).mockResolvedValueOnce({ data: { text: 'Current statement.' } });
    rerender(<ClaimCorrectionEditor claimIds={['current']} onSaved={onSaved} />);
    await screen.findByDisplayValue('Current statement.');
    await act(async () => { oldResponse({ data: { text: 'Obsolete statement.' } }); });
    expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('Current statement.');
  });
});
