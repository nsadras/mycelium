import { afterEach, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { MemoryWorkspace } from '../lib/api';
import EvidenceWorkspace from './EvidenceWorkspace';

afterEach(cleanup);

const workspace: MemoryWorkspace = {
  revision: 1, request: 'Preferences?', operations: [], remaining_searches: 2,
  remaining_evidence_tokens: 2000, last_operation_status: 'complete',
  evidence: {
    more_available: false,
    records: [{ revision: 1, record_id: 'c1', record_type: 'claim', statement: 'An old interpretation', claim_ids: ['c1'], state: 'canonical' }],
    sources: [{ revision: 1, source_id: 's1', conversation_time: '2026-01-01', status: 'active',
      citations: [{ claim_id: 'c1', segment_ids: ['seg1'] }],
      segments: [{ segment_id: 'seg1', relationship: 'cited', content: 'Original wording', index: 0 }] }],
  },
};

it('shows exact citations and replaces obsolete interpretation and source text', async () => {
  const view = render(<EvidenceWorkspace workspace={workspace} />);
  await userEvent.click(screen.getByRole('button', { name: /Evidence workspace/ }));
  expect(screen.getByText('Claim c1 cites seg1')).toBeTruthy();
  expect(screen.getByText('seg1 · cited')).toBeTruthy();
  const next = structuredClone(workspace);
  next.revision = 2;
  next.evidence.records[0].statement = 'Corrected interpretation';
  next.evidence.records[0].state = 'superseded';
  next.evidence.sources[0].segments[0].content = 'Corrected wording';
  next.evidence.sources[0].status = 'retracted';
  next.evidence.sources[0].retraction_reason = 'Imported in error';
  view.rerender(<EvidenceWorkspace workspace={next} />);
  expect(screen.queryByText('An old interpretation')).toBeNull();
  expect(screen.queryByText('Original wording')).toBeNull();
  expect(screen.getByText('Corrected wording')).toBeTruthy();
  expect(screen.getByText('claim · c1 · superseded')).toBeTruthy();
  expect(screen.getByText('Source status: retracted — Imported in error')).toBeTruthy();
});

it('shows the latest failure when detailed operation history was elided', async () => {
  render(<EvidenceWorkspace workspace={{ ...workspace, last_operation_status: 'failed' }} />);
  await userEvent.click(screen.getByRole('button', { name: /Evidence workspace/ }));
  expect(screen.getByText('Latest memory operation failed')).toBeTruthy();
});


it('shows assigned identities and their distinct roles on an unpublished claim', async () => {
  const next = structuredClone(workspace);
  next.evidence.records[0].subjects = [
    { entity_id: 'person-a', name: 'Rene', role: 'subject', aliases: ['R. Bell'] },
    { entity_id: 'person-b', name: 'Rene', role: 'context', aliases: ['R. Hale'] },
  ];
  render(<EvidenceWorkspace workspace={next} />);
  await userEvent.click(screen.getByRole('button', { name: /Evidence workspace/ }));
  expect(screen.getByText('Rene · subject · also known as R. Bell')).toBeTruthy();
  expect(screen.getByText('Rene · context · also known as R. Hale')).toBeTruthy();
});
