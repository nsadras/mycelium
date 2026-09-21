"""Mechanical evidence invariants; these tests do not establish model quality."""

from copy import deepcopy
import json
from unittest.mock import AsyncMock

import pytest

from mycelium.memory_inputs import PASSAGE_CHARACTERS, compact_retention
from mycelium.materialization import sections_markdown
from mycelium.source_references import segment_references
from mycelium import Mycelium, SourceInput
from mycelium.artifacts import SourceSegment
from mycelium.telemetry import trace_metadata


def payload():
    return {'occurred_at': '2035-01-01', 'segments': [
        {'id': f'source#seg-{i}', 'index': i, 'text': f'Literal fragment {i}.',
         'source_id': 'source', 'speaker': 'Speaker', 'participant_id': 'participant',
         'role': None, 'source_time': '2035-01-01', 'metadata': {'engram_segment_id': i}}
        for i in range(3)], 'context_segments': [], 'new_subject_ids': ['new-person'],
        'existing_subjects': [], 'prior_memories': [],
        'participants': [{'id': 'participant', 'name': 'Speaker', 'subject_id': None}]}


def test_passage_round_trip_and_duplicate_citations():
    data = payload()
    original = deepcopy(data)
    compact, ids = compact_retention(data)
    row, = compact['segments']
    assert row['text'] == ' '.join(s['text'] for s in data['segments'])
    assert 'index' not in row and 'source_id' not in row
    assert ids.citations[row['id']] == [s['id'] for s in data['segments']]
    result = ids.retention({'subjects': [], 'memories': [{'id': 'm1', 'text': 'Literal r0.',
        'segment_ids': [row['id'], row['id']], 'subject_ids': []}], 'changes': []})
    assert result['memories'][0]['segment_ids'] == [s['id'] for s in data['segments']]
    assert result['memories'][0]['text'] == 'Literal r0.'
    assert data == original


@pytest.mark.parametrize(('field', 'value'), [
    ('source_id', 'other-source'), ('participant_id', 'other-participant'),
    ('speaker', 'Other Speaker'), ('role', 'assistant'), ('source_time', '2035-01-02'),
    ('metadata', {'note': 'Distinct source annotation'}), ('index', 7), ('index', None),
])
def test_exact_boundaries_prevent_joining(field, value):
    data = payload()
    data['segments'][1][field] = value
    compact, ids = compact_retention(data)
    assert len(compact['segments']) == 3
    assert [ids.citations[r['id']] for r in compact['segments']] == [[s['id']] for s in data['segments']]


def test_context_and_new_evidence_do_not_join():
    data = payload()
    data['context_segments'] = data['segments'][1:]
    data['segments'] = data['segments'][:1]
    compact, ids = compact_retention(data)
    assert len(compact['segments']) == len(compact['context_segments']) == 1
    assert ids.citations[compact['segments'][0]['id']] == ['source#seg-0']
    assert ids.citations[compact['context_segments'][0]['id']] == ['source#seg-1', 'source#seg-2']


def test_size_bound_preserves_existing_long_segment_without_splitting():
    data = payload()
    data['segments'][0]['text'] = 'a' * (PASSAGE_CHARACTERS - 1)
    data['segments'][1]['text'] = 'b' * (PASSAGE_CHARACTERS + 1)
    compact, ids = compact_retention(data)
    assert [s['text'] for s in compact['segments']] == [s['text'] for s in data['segments']]
    assert len(ids.citations) == 3


def test_citation_display_compresses_exact_runs_without_filling_gaps():
    source = 'source-opaque'
    segments = tuple(f'{source}#seg-{i:04d}' for i in (1, 2, 3, 7, 9, 10))
    assert segment_references(source, segments) == (
        '`source-opaque#seg-0001`–`source-opaque#seg-0003` · `source-opaque#seg-0007` · '
        '`source-opaque#seg-0009`–`source-opaque#seg-0010`')
    # References outside the canonical numbered format remain literal.
    opaque = ('source-opaque#seg-01', 'source-opaque#seg-02', 'custom-id', 'another#seg-0003')
    assert segment_references(source, opaque) == ' · '.join(f'`{sid}`' for sid in opaque)
    assert segment_references(source, ('<untrusted&identifier>',)) == '`&lt;untrusted&amp;identifier&gt;`'
    sections = [{'title': 'Notes', 'items': [{'kind': 'fact', 'text': 'A retained statement.',
        'sources': [{'source_id': source, 'segment_ids': list(segments)}]}]}]
    before = deepcopy(sections)
    markdown = sections_markdown(sections)
    assert '[^e1]: `source-opaque` · ' + segment_references(source, segments) in markdown
    assert sections == before


@pytest.mark.asyncio
async def test_build_expands_passages_before_persistence_and_keeps_diagnostic_map(tmp_path, monkeypatch):
    with Mycelium(tmp_path) as memory:
        monkeypatch.setattr(memory.retriever.claim_index, 'search', AsyncMock(return_value=[]))
        fragments = ('I can review', 'the plan after the revision.', 'I will send', 'the revision on Friday.')
        capture = await memory.ingest_source(SourceInput(' '.join(fragments), 'meeting',
            source_type='meeting_transcript', occurred_at='2035-01-01', participants=('Ari', 'Bo'),
            segments=tuple(SourceSegment('', i, text, speaker='Ari' if i < 2 else 'Bo',
                participant_id='speaker-0' if i < 2 else 'speaker-1') for i, text in enumerate(fragments))))
        source = memory.artifacts.get_source(capture.source_ids[0])
        source_before = deepcopy(source)
        original_ids = [s.segment_id for s in source.segments]

        def respond(system, user, schema, **kwargs):
            data = json.loads(user)
            if kwargs['debug_label'] == 'memory-retention':
                first, second = data['segments']
                assert [r['text'] for r in data['segments']] == [' '.join(fragments[:2]), ' '.join(fragments[2:])]
                assert trace_metadata()['request_citations'] == {first['id']: original_ids[:2], second['id']: original_ids[2:]}
                assert schema['$defs']['MemorySelection']['properties']['segment_ids']['items']['enum'] == sorted([first['id'], second['id']])
                subjects = [dict(id=sid, title=participant['name'], entity_type='person', participant_ids=[participant['id']])
                            for sid, participant in zip(data['new_subject_ids'], data['participants'])]
                return {'subjects': subjects, 'memories': [
                    {'id': 'm1', 'text': 'Ari can review the plan after Bo sends the revision.',
                     'subject_ids': [s['id'] for s in subjects], 'segment_ids': [first['id'], second['id']]},
                    {'id': 'invalid', 'text': 'A structurally invalid citation.', 'subject_ids': [], 'segment_ids': ['missing']},
                ], 'changes': []}
            return {'items': [{'owner_id': data['affected_subject_ids'][0], 'heading': 'Plan review',
                 'memory_ids': [data['memories'][0]['id']],
                'linked_subject_ids': [], 'state': 'current'}]}

        memory.llm.call_structured = AsyncMock(side_effect=respond)
        result = await memory.consolidate()
        assert not result.report.failures and len(result.report.warnings) == 1
        assert 'request_citations' not in result.report.warnings[0]
        claim, = memory.artifacts.list_claims()
        assert [sid for p in claim.provenance for sid in p.segment_ids] == original_ids
        assert [p.speaker for p in claim.provenance] == ['Ari', 'Bo']
        assert memory.artifacts.get_source(source.source_id) == source_before
        batch = memory.artifacts.list_episodes()[0].extraction_batches[0]
        assert sorted(sid for ids in batch.response['_rejections'][0]['request_citations'].values() for sid in ids) == original_ids
        await memory.consolidate()
        assert memory.llm.call_structured.await_count == 2
