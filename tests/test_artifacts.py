from datetime import datetime

import pytest
from unittest.mock import AsyncMock

from mycelium.artifacts import ArtifactStore, ClaimProvenance, ClaimReconciler, MemoryClaim, normalize_temporal_facets
from mycelium.config import Config
from mycelium.encoder import Encoder
from mycelium.store import LogStore, WikiStore


@pytest.mark.asyncio
async def test_encoder_persists_source_episode_and_atomic_claims(tmp_path):
    llm = AsyncMock()
    llm.call_structured.return_value = {
        "summary": "Ava described a preference and a plan.",
        "claims": [
            {
                "text": "Ava prefers tea.", "kind": "preference",
                "about": [{"entity": "Ava", "role": "person"}],
                "segment_ids": ["source-fixed-later"],
                "confidence": 0.9, "facets": {"object": "tea"},
            }
        ],
    }
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(llm, WikiStore(tmp_path / "wiki"), LogStore(tmp_path / "logs"), Config.defaults(), artifacts)

    # Make the mock use the generated segment id returned in the extraction prompt.
    async def response(system, user, output_type, **kwargs):
        segment_id = user.split("[", 1)[1].split("]", 1)[0]
        value = dict(llm.call_structured.return_value)
        value["claims"] = [dict(value["claims"][0], segment_ids=[segment_id])]
        return value
    llm.call_structured.side_effect = response

    await encoder.encode_session(
        "[D1:1] (2024-01-10) Ava: I prefer tea.", "session-1",
        source_type="benchmark_conversation", occurred_at="2024-01-10",
    )

    source = artifacts.list_sources()[0]
    episode = artifacts.list_episodes()[0]
    claim = artifacts.list_claims()[0]
    assert source.segments[0].content == "I prefer tea."
    assert episode.extraction_status == "complete"
    assert claim.provenance[0].segment_ids == [source.segments[0].segment_id]
    assert artifacts.coverage_report()["segment_coverage"] == 1.0


def test_reconciler_merges_duplicates_and_supersedes_slots(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    reconcile = ClaimReconciler(store).reconcile
    common = dict(
        kind="preference", about=[{"entity": "Ava"}], recorded_at=datetime.now().isoformat(),
        provenance=[ClaimProvenance("source-1", ["source-1#seg-0001"])],
    )
    first = reconcile(MemoryClaim(claim_id="claim-1", text="Ava prefers tea.", slot="favorite_drink", **common))
    duplicate = reconcile(MemoryClaim(claim_id="claim-2", text="Ava prefers tea.", slot="favorite_drink", **common))
    replacement = reconcile(MemoryClaim(claim_id="claim-3", text="Ava now prefers coffee.", slot="favorite_drink", **common))

    assert duplicate.claim_id == first.claim_id
    assert store.get_claim("claim-1").status == "superseded"
    assert replacement.links[0]["relation"] == "supersedes"


def test_locomo_style_timestamp_anchors_relative_dates():
    facets = normalize_temporal_facets(
        {"when": "yesterday"}, "4:24 pm on 16 March, 2023"
    )
    assert facets["observed_at"] == "4:24 pm on 16 March, 2023"
    assert facets["normalized_date"] == "2023-03-15"
