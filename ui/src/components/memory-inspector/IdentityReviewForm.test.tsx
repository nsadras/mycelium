import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import api, { type EntityRecord, type EntityResolutionDecisionArtifact } from '../../lib/api';
import IdentityReviewForm from './IdentityReviewForm';

vi.mock('../../lib/api', () => ({ default: { get: vi.fn() } }));
afterEach(cleanup);
beforeEach(() => { vi.resetAllMocks(); });

const decision = {
  decision_id: 'decision', entity_id: 'first', proposed_entity_type: 'person',
  proposed_title: 'Sam', supporting_claim_ids: ['claim'], review_state: 'accepted',
} as EntityResolutionDecisionArtifact;
const entities = [
  { entity_id: 'first', title: 'Sam', entity_type: 'person', status: 'active' },
  { entity_id: 'second', title: 'Samuel Porter', entity_type: 'person', status: 'active' },
] as EntityRecord[];

it('corrects an accepted identity with scoped wording and leaves the selected name intact', async () => {
  vi.mocked(api.get).mockResolvedValue({ data: { claim_id: 'claim', status: 'active', text: 'Sam made the checklist.' } });
  const user = userEvent.setup();
  const review = vi.fn(async () => {});
  render(<IdentityReviewForm decision={decision} entities={entities} entityTypes={[]} reviewNote="" reviewing={null} setReviewNote={vi.fn()} review={review} />);
  await screen.findByDisplayValue('Sam made the checklist.');
  await user.selectOptions(screen.getByLabelText('Identity'), 'second');
  await user.clear(screen.getByLabelText('Statement 1'));
  await user.type(screen.getByLabelText('Statement 1'), 'Samuel Porter made the checklist.');
  await user.click(screen.getByRole('button', { name: 'Save identity correction' }));
  expect(review).toHaveBeenCalledWith('approve', {
    entity_id: 'second', entity_type: 'person', scope: 'independent', page_state: 'provisional',
    claim_texts: { claim: 'Samuel Porter made the checklist.' },
  });
  expect(screen.queryByLabelText('Name')).toBeNull();
});

it('blocks saving when supporting statements cannot be loaded', async () => {
  vi.mocked(api.get).mockRejectedValue(new Error('Unavailable'));
  const review = vi.fn(async () => {});
  render(<IdentityReviewForm decision={decision} entities={entities} entityTypes={[]} reviewNote="" reviewing={null} setReviewNote={vi.fn()} review={review} />);
  await screen.findByRole('alert');
  expect((screen.getByRole('button', { name: 'Save identity correction' }) as HTMLButtonElement).disabled).toBe(true);
  expect(review).not.toHaveBeenCalled();
});

it('submits an explicit new identity and applies no-page only to its reviewed evidence', async () => {
  vi.mocked(api.get).mockResolvedValue({ data: { claim_id: 'claim', status: 'active', text: 'Sam made the checklist.' } });
  const user = userEvent.setup();
  const review = vi.fn(async () => {});
  render(<IdentityReviewForm decision={decision} entities={entities} entityTypes={[]} reviewNote="" reviewing={null} setReviewNote={vi.fn()} review={review} />);
  await screen.findByDisplayValue('Sam made the checklist.');
  await user.selectOptions(screen.getByLabelText('Identity'), '');
  await user.click(screen.getByRole('checkbox'));
  await user.click(screen.getByRole('button', { name: 'Save identity correction' }));
  await waitFor(() => expect(review).toHaveBeenCalledWith('approve', {
    entity_id: '', entity_type: 'person', title: 'Sam', scope: 'context', page_state: 'no_page', claim_texts: {},
  }));
});
