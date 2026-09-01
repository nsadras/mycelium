from datetime import datetime

import pytest

from mycelium.artifacts import (
    ArtifactStore,
    ClaimPlacement,
    ClaimProvenance,
    ClaimScopeDecision,
    ConsolidatedFact,
    DreamClaimDecision,
    DreamRunAudit,
    MemoryClaim,
    ScopeCohort,
)
from mycelium.config import Config
from mycelium.dream_commit import DreamCommitService
from mycelium.materialization import MaterializationResult, PageMaterializer
from mycelium.models import LogEntry
from mycelium.store import LogStore, WikiStore


NOW = "2026-08-31T15:00:00-07:00"


def test_interrupted_dream_commit_replays_to_one_consistent_projection(
    tmp_path,
    monkeypatch,
):
    artifact_path = tmp_path / "artifacts"
    wiki_path = tmp_path / "wiki"
    log_path = tmp_path / "logs"
    artifacts = ArtifactStore(artifact_path)
    wiki = WikiStore(wiki_path)
    logs = LogStore(log_path)
    materializer = PageMaterializer(wiki, artifacts, Config.defaults())
    entity = artifacts.create_entity("you", "You")
    claim = MemoryClaim(
        claim_id="claim-1",
        text="The user prefers written project updates.",
        about=[{"entity": "user"}],
        provenance=[ClaimProvenance(
            "source-1", ["source-1#seg-0001"], "2026-08-31#session-1"
        )],
        recorded_at=NOW,
        claim_type="preference",
        predicate="prefers",
    )
    artifacts.save_claim(claim)
    logs.append(LogEntry(
        entry_id="2026-08-31#session-1",
        session_id="session-1",
        timestamp=datetime.fromisoformat(NOW),
        content="Raw evidence",
    ))
    placement = ClaimPlacement(
        claim_id=claim.claim_id,
        owner_entity_id=entity.entity_id,
        section_key="preferences_working_style",
        linked_entity_ids=[],
        status="placed",
        reason="The claim belongs to the user profile.",
        created_at=NOW,
        updated_at=NOW,
    )
    fact = ConsolidatedFact(
        fact_id="fact-1",
        text=claim.text,
        member_claim_ids=[claim.claim_id],
        owner_entity_id=entity.entity_id,
        section_key="preferences_working_style",
        state="current",
        linked_entity_ids=[],
        synthesis_origin="claim",
        confidence=0.9,
        reason="Direct projection.",
        created_at=NOW,
        updated_at=NOW,
    )
    scope = ClaimScopeDecision(
        decision_id="scope-dream-1-claim-1",
        claim_id=claim.claim_id,
        owner_entity_id=entity.entity_id,
        section_key="preferences_working_style",
        linked_entity_ids=[],
        supporting_claim_ids=[claim.claim_id],
        confidence=0.9,
        reason="The claim belongs to the user profile.",
        origin="automatic",
        dream_run_id="dream-1",
        status="active",
        created_at=NOW,
    )
    cohort = ScopeCohort(
        cohort_id="cohort-dream-1",
        dream_run_id="dream-1",
        claim_ids=[claim.claim_id],
        source_ids=["source-1"],
        revision_entity_ids=[],
        created_at=NOW,
    )
    audit = DreamRunAudit(
        run_id="dream-1",
        started_at=NOW,
        completed_at=NOW,
        status="completed",
        source_ids=["2026-08-31#session-1"],
        completed_source_ids=["2026-08-31#session-1"],
        pending_source_ids=[],
        pages_created=1,
        pages_updated=0,
        claim_decisions=[DreamClaimDecision(
            claim_id=claim.claim_id,
            evidence_id="claim-1::claim",
            source_id="source-1",
            raw_log_entry_id="2026-08-31#session-1",
            disposition="routed",
            reason="Owned by you.",
            page_slugs=["you"],
        )],
    )
    service = DreamCommitService(artifacts, logs, materializer)
    commit = service.prepare(
        run_id="dream-1",
        materialization=MaterializationResult(
            entities={entity.entity_id: entity},
            placements={claim.claim_id: placement},
            facts={fact.fact_id: fact},
        ),
        retention_records=[],
        entity_decisions=[],
        maturity_assessments=[],
        entity_references=[],
        encounters=[],
        scope_decisions=[scope],
        proposals=[],
        cohort=cohort,
        affected_entity_ids={"you"},
        completed_log_entry_ids=["2026-08-31#session-1"],
        audit=audit,
    )
    original_persist_audit = artifacts.persist_dream_audit
    interrupted = False

    def fail_before_audit(record):
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            raise OSError("simulated process interruption before audit")
        original_persist_audit(record)

    monkeypatch.setattr(artifacts, "persist_dream_audit", fail_before_audit)
    with pytest.raises(OSError, match="simulated process interruption"):
        service.apply(commit)

    assert artifacts.get_dream_commit(commit.commit_id).status == "applying"
    assert artifacts.get_dream_commit(commit.commit_id).error
    assert len(artifacts.list_consolidated_facts()) == 1
    assert wiki.exists("you")
    first_page_version = wiki.get("you").version
    assert logs.get("2026-08-31#session-1").consolidated is True

    restarted_artifacts = ArtifactStore(artifact_path)
    restarted_wiki = WikiStore(wiki_path)
    restarted_logs = LogStore(log_path)
    restarted_service = DreamCommitService(
        restarted_artifacts,
        restarted_logs,
        PageMaterializer(
            restarted_wiki, restarted_artifacts, Config.defaults()
        ),
    )
    assert restarted_service.recover_pending() == [commit.commit_id]

    assert restarted_artifacts.get_dream_commit(commit.commit_id).status == "complete"
    assert len(restarted_artifacts.list_consolidated_facts()) == 1
    assert len(restarted_artifacts.list_scope_decisions()) == 1
    assert len(restarted_artifacts.list_scope_cohorts()) == 1
    assert len(restarted_artifacts.list_dream_runs()) == 1
    assert restarted_artifacts.get_claim(claim.claim_id).dream_disposition == "routed"
    assert restarted_wiki.get("you").version == first_page_version
    assert restarted_logs.get("2026-08-31#session-1").consolidated is True
