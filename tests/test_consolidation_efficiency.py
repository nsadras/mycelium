"""Lossless batching, context budgets, and removal of empty truth work."""

import json
from collections import Counter
from itertools import product
from typing import get_args
from unittest.mock import AsyncMock

import pytest

from mycelium.batching import structured_input_budget
from mycelium.budget import count_tokens
from mycelium.facts import FactResolver
from tests.memory_helpers import claim, fact, place, setup_owner


def selection_fixture(
    tmp_path, incoming_count=5, prior_count=25, words=0, context=32768
):
    artifacts = setup_owner(tmp_path)
    prior = [
        claim(
            f"old-{i}",
            f"The user recorded observation {i}. " + "detail " * words,
            "2026-01-01",
        )
        for i in range(prior_count)
    ]
    incoming = [
        claim(f"new-{i}", f"The user recorded a new observation {i}.", "2026-02-01")
        for i in range(incoming_count)
    ]
    placements = {c.claim_id: place(artifacts, c) for c in [*prior, *incoming]}
    llm = AsyncMock(context_window_tokens=context)
    return FactResolver(llm, artifacts), incoming, placements, [fact(c) for c in prior]


@pytest.mark.asyncio
@pytest.mark.parametrize("context,words", [(32768, 0), (8192, 250)])
async def test_batched_selection_covers_each_pair_once_within_budget(
    tmp_path, context, words
):
    resolver, incoming, placements, prior = selection_fixture(
        tmp_path, words=words, context=context
    )
    pairs = Counter()
    expected_selected = {c.claim_id: set() for c in incoming}

    async def respond(system, user, schema, **kwargs):
        aliases = schema.model_fields["decisions"].annotation.model_fields
        decision = next(iter(aliases.values())).annotation
        targets = get_args(
            get_args(decision.model_fields["candidate_fact_ids"].annotation)[0]
        )
        pairs.update(product(aliases, targets))
        assert count_tokens(
            system + "\n" + user + "\n" + json.dumps(schema.model_json_schema())
        ) <= structured_input_budget(context, kwargs["num_predict"])
        for alias in aliases:
            expected_selected[incoming[int(alias[1:]) - 1].claim_id].add(
                prior[int(targets[0][1:]) - 1].fact_id
            )
        return {
            "decisions": {
                alias: {
                    "candidate_fact_ids": [targets[0]],
                    "reason": "Fixture decision.",
                }
                for alias in aliases
            }
        }

    resolver.llm.call_structured.side_effect = respond
    result = await resolver._select_prior_facts(incoming, placements, prior, {})
    assert result == expected_selected
    assert pairs == Counter(
        product([f"C{i:03d}" for i in range(1, 6)], [f"X{i:03d}" for i in range(1, 26)])
    )
    if words == 0:
        assert resolver.llm.call_structured.await_count == 3  # All five incoming claims share each prior-fact chunk.
    else:
        assert resolver.llm.call_structured.await_count > 3


@pytest.mark.asyncio
async def test_oversized_single_pair_is_not_silently_truncated(tmp_path):
    resolver, incoming, placements, prior = selection_fixture(
        tmp_path, 1, 1, words=10000, context=8192
    )
    with pytest.raises(ValueError, match="evidence was not truncated"):
        await resolver._select_prior_facts(incoming, placements, prior, {})
    resolver.llm.call_structured.assert_not_awaited()


@pytest.mark.asyncio
async def test_new_memories_do_not_require_empty_target_truth_calls(tmp_path):
    resolver, incoming, placements, _ = selection_fixture(tmp_path, 2, 0)

    async def respond(_system, _user, _schema, **kwargs):
        assert kwargs["debug_label"] == "dream-fact-synthesis"
        return {
            "facts": [
                {"prominence": "briefing", 'memory_scope': 'An independent observation.', 'member_claim_aliases': [f'C{i:03d}'], 'state': 'current', 'section_key': 'preferences_working_style', 'text': None}
                for i, c in enumerate(incoming, 1)
            ]
        }

    resolver.llm.call_structured.side_effect = respond
    result = await resolver.resolve(
        list(placements.values()),
        affected_entity_ids={"you"},
        incoming_claim_ids={c.claim_id for c in incoming},
        dream_run_id="test",
    )
    assert not result.failures
    assert {c for f in result.facts for c in f.member_claim_ids} == {
        c.claim_id for c in incoming
    }
    assert resolver.llm.call_structured.await_count == 1


def test_truth_batch_requires_each_decision_and_rejects_competing_changes():
    from pydantic import ValidationError
    from mycelium.structured_outputs import fact_truth_batch_model
    schema = fact_truth_batch_model({'N1': ['P1'], 'N2': ['P1', 'P2']})
    first = {'comparisons': [{'target': 'P1', 'scope': 'same', 'reason': 'Same object.'}],
             'relation': 'supersedes', 'changed_targets': ['P1'], 'reason': 'Explicit replacement.'}
    second = {'comparisons': [{'target': 'P1', 'scope': 'same', 'reason': 'Additional evidence.'},
                              {'target': 'P2', 'scope': 'distinct', 'reason': 'Another object.'}],
              'relation': 'no_change', 'changed_targets': [], 'reason': 'The change is already proposed by N1.'}
    assert schema.model_validate({'decisions': {'N1': first, 'N2': second}})
    with pytest.raises(ValidationError):
        schema.model_validate({'decisions': {'N1': first}})
    with pytest.raises(ValidationError, match='only one change'):
        schema.model_validate({'decisions': {'N1': first, 'N2': {**second, 'relation': 'supersedes', 'changed_targets': ['P1']}}})
    with pytest.raises(ValidationError, match='same scope'):
        schema.model_validate({'decisions': {'N1': first, 'N2': {**second, 'relation': 'supersedes', 'changed_targets': ['P2']}}})
