"""Finite fresh-store temporal acceptance through the real memory lifecycle."""

import asyncio
from dataclasses import asdict
import time

from mycelium import Mycelium
from mycelium.artifacts import SourceSegment
from mycelium.claim_lifecycle import ClaimLifecycleService
from mycelium.facts import FactResolver
from mycelium.materialization import PageMaterializer
from mycelium.operations import SourceInput, ConsolidationRequest, RetrievalRequest
from mycelium.snapshots import snapshot_store, export_records
from mycelium.telemetry import trace_operation
from benchmarks.experiments.probe_support import fresh_run_root, write


async def main():
    root = fresh_run_root("temporal-pipeline")
    root.mkdir(parents=True)
    started = time.monotonic()
    outcome = {
        "status": "running",
        "acceptance_scope": "Temporal date/provenance mechanics only; inspect snapshots separately for semantic coverage and coherence.",
        "steps": [],
    }
    write(root / "result.json", outcome)
    print("OUTPUT", root, flush=True)
    try:
        with Mycelium(
            root / "store", config_path="mycelium.toml", memory_profile="none"
        ) as mem:
            write(root / "config.json", asdict(mem.config))
            call = mem.llm.call_structured
            call_number = 0

            async def recorded_call(system, user, schema, **kwargs):
                nonlocal call_number
                call_number += 1
                path = root / "requests" / f"{call_number:03d}.json"
                record = {
                    "system": system,
                    "user": user,
                    "schema": schema.model_json_schema(),
                    "options": kwargs,
                }
                write(path, record)
                try:
                    result = await call(system, user, schema, **kwargs)
                    record["response"] = result
                    return result
                except Exception as exc:
                    record["error"] = f"{type(exc).__name__}: {exc}"
                    raise
                finally:
                    write(path, record)

            mem.llm.call_structured = recorded_call
            text = "Niko will deliver the sculpture in three days, provided payment arrives tomorrow."
            with trace_operation("temporal_pipeline_ingest"):
                ingest = await mem.ingest_source(
                    SourceInput(
                        transcript=text,
                        session_id="temporal-delivery",
                        participants=("Niko",),
                        occurred_at="2026-08-31T10:00:00-07:00",
                        segments=(
                            SourceSegment(
                                "",
                                0,
                                text,
                                speaker="Niko",
                                role="user",
                                timestamp="2026-06-10T23:55:00-07:00",
                            ),
                        ),
                    )
                )
                build = await mem.consolidate(ConsolidationRequest())
            write(root / "ingestion.json", asdict(ingest))
            write(root / "build.json", asdict(build))
            claims = mem.artifacts.list_claims(status="active")
            write(root / "encoded-claims.json", [asdict(claim) for claim in claims])
            snapshot_store(mem.store_path, root / "encoded-snapshot")
            times = [t for c in claims for t in c.facets.get("temporal", [])]
            assert any(
                t["role"] == "event_time" and t["start"] == "2026-06-13" for t in times
            ), times
            assert any(
                t["role"] in {"deadline", "condition_time"}
                and t["start"] == "2026-06-11"
                for t in times
            ), times
            assert all(
                e.extraction_status == "complete" for e in mem.artifacts.list_episodes()
            )
            outcome["steps"].append(
                "encoding uses message dates and retains both action times"
            )

            with trace_operation("temporal_pipeline_retrieval"):
                retrieved = await mem.retrieve_context(
                    RetrievalRequest(
                        "When will Niko deliver the sculpture, and when must payment arrive?"
                    )
                )
            write(root / "initial-retrieval.json", asdict(retrieved))
            assert (
                "2026-06-13" in retrieved.rendered_context
                and "2026-06-11" in retrieved.rendered_context
            )
            outcome["steps"].append("retrieval contains both times")

            target = next(
                c
                for c in claims
                if any(t["role"] == "event_time" for t in c.facets.get("temporal", []))
            )
            service = ClaimLifecycleService(
                mem.artifacts,
                PageMaterializer(mem.wiki, mem.artifacts, mem.config),
                FactResolver(mem.llm, mem.artifacts, mem.config),
            )
            with trace_operation("temporal_pipeline_correction"):
                review = await service.correct_claim(
                    target.claim_id,
                    "Niko will deliver the sculpture in two days, provided payment arrives tomorrow.",
                    reason="Correct the duration in the original account.",
                )
                write(root / "correction-preview.json", asdict(review))
                assert mem.artifacts.get_claim(target.claim_id).status == "active"
                choices = {
                    t["time_id"]: next(
                        o["reference_id"]
                        for o in t["options"]
                        if o["reference_id"].startswith("T")
                    )
                    for t in review.times
                }
                corrected = await service.correct_claim(
                    target.claim_id,
                    "Niko will deliver the sculpture in two days, provided payment arrives tomorrow.",
                    reason="Correct the duration in the original account.",
                    draft_id=review.draft_id,
                    time_references=choices,
                )
            replacement = mem.artifacts.get_claim(corrected.claim_ids[0])
            write(root / "correction.json", asdict(replacement))
            times = replacement.facets["temporal"]
            assert any(
                t["role"] == "event_time" and t["start"] == "2026-06-12" for t in times
            ), times
            assert any(
                t["role"] in {"condition_time", "deadline"}
                and t["start"] == "2026-06-11"
                for t in times
            ), times
            assert mem.artifacts.get_claim(target.claim_id).status == "superseded"
            assert all(
                t["anchor_segment_id"] != t["evidence_segment_id"] for t in times
            )
            outcome["steps"].append(
                "correction retains original reference dates and explicit evidence"
            )
            snapshot_store(mem.store_path, root / "corrected-snapshot")

            with trace_operation("temporal_pipeline_new_plan"):
                review = await service.correct_claim(
                    replacement.claim_id,
                    "This is a new plan from this correction: Niko will deliver the sculpture in two days.",
                    reason="A new plan relative to submission.",
                )
                write(root / "new-plan-preview.json", asdict(review))
                amended = await service.correct_claim(
                    replacement.claim_id,
                    "This is a new plan from this correction: Niko will deliver the sculpture in two days.",
                    reason="A new plan relative to submission.",
                    draft_id=review.draft_id,
                    time_references={t["time_id"]: "submission" for t in review.times},
                )
            new_plan = mem.artifacts.get_claim(amended.claim_ids[0])
            write(root / "new-plan.json", asdict(new_plan))
            times = new_plan.facets["temporal"]
            expected = next(
                option["start"]
                for option in review.times[0]["options"]
                if option["reference_id"] == "submission"
            )
            assert len(times) == 1 and times[0]["start"] == expected, times
            assert times[0]["anchor_segment_id"] == times[0]["evidence_segment_id"]
            outcome["steps"].append("explicit new plan uses submission date")
            with trace_operation("temporal_pipeline_updated_retrieval"):
                retrieved = await mem.retrieve_context(
                    RetrievalRequest(
                        "When is Niko now planning to deliver the sculpture?"
                    )
                )
            write(root / "updated-retrieval.json", asdict(retrieved))
            assert new_plan.claim_id in retrieved.evidence.claim_ids
            snapshot_store(mem.store_path, root / "final-snapshot")
            export_records(mem.store_path, root / "export")
            outcome["steps"].append(
                "updated retrieval and snapshots preserve current evidence"
            )
            outcome["status"] = "complete"
    except Exception as exc:
        outcome.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        outcome["elapsed_seconds"] = time.monotonic() - started
        write(root / "result.json", outcome)
        print(outcome, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
