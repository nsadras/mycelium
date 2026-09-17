"""Bounded configured-model proof; results require source review, not a score."""

import asyncio
import json
import time
from dataclasses import asdict
from pathlib import Path

from benchmarks.experiments import compact_contract as contract
from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.model_recording import RecordingClient
from mycelium import Mycelium
from mycelium.telemetry import trace_operation


CASES = [
    {
        "source_type": "meeting_transcript", "occurred_at": "2032-04-12T10:00:00",
        "segments": [
            {"id": "a1", "speaker": "Mara", "role": "participant", "text": "I can deliver the pottery kiln on April 18, but only after Niko checks the wiring."},
            {"id": "a2", "speaker": "Niko", "role": "participant", "text": "I can do that on April 16. I can't transport it."},
            {"id": "a3", "speaker": "Mara", "role": "participant", "text": "Good, let's use that plan, provided the check passes."},
        ],
    },
    {
        "source_type": "meeting_transcript", "occurred_at": "2032-04-14T11:00:00",
        "segments": [
            {"id": "b1", "speaker": "Niko", "role": "participant", "text": "For the same kiln: move my wiring check from April 16 to April 17. The delivery still depends on it passing."},
            {"id": "b2", "speaker": "Mara", "role": "participant", "text": "Understood. On another topic, I've started learning the clarinet."},
            {"id": "b3", "speaker": "Mara", "role": "participant", "text": "I also met a librarian called Niko yesterday, a different person from you. He suggested an archive visit; I haven't decided whether to go."},
            {"id": "b4", "speaker": "Niko", "role": "participant", "text": "I visited that archive in June 2031. Last week I went to the local studio, and I might return next month, but nothing is booked."},
        ],
    },
    {
        "source_type": "agent_conversation", "occurred_at": "2032-04-15T09:00:00",
        "segments": [
            {"id": "c1", "speaker": "You", "role": "user", "text": "I live in Dundee and I am undecided about moving."},
            {"id": "c2", "speaker": "Assistant", "role": "assistant", "text": "You could move to Stirling and sell your car."},
            {"id": "c3", "speaker": "You", "role": "user", "text": "Neither is a decision I've made. I would like to compare commuting costs first."},
        ],
    },
]


class BudgetExceeded(asyncio.CancelledError):
    pass


class BudgetClient:
    def __init__(self, client, seconds, calls):
        self.client, self.limit = client, calls
        self.deadline, self.calls = time.monotonic() + seconds, 0

    def __getattr__(self, name):
        return getattr(self.client, name)

    async def chat(self, **request):
        remaining = self.deadline - time.monotonic()
        if self.calls >= self.limit or remaining <= 0:
            raise BudgetExceeded("Fixed experiment budget exhausted")
        self.calls += 1
        async with asyncio.timeout(remaining):
            return await self.client.chat(**request)


def metrics(root):
    records = [json.loads(p.read_text()) for p in root.rglob("requests/*.json")]
    responses = [r["response"] for r in records if "response" in r]
    return {
        "attempts": len(records), "transport_failures": sum(r["status"] != "complete" for r in records),
        "input_tokens": sum(r.get("prompt_eval_count", 0) for r in responses),
        "output_tokens": sum(r.get("eval_count", 0) for r in responses),
        "server_seconds": sum(r.get("total_duration", 0) for r in responses) / 1e9,
        "client_seconds": sum(r.get("seconds", 0) for r in records),
    }


async def main():
    root = fresh_run_root("compact-contract")
    root.mkdir(parents=True)
    print("OUTPUT", root, flush=True)
    for module in (Path(__file__), Path(contract.__file__)):
        (root / module.name).write_text(module.read_text())
    write(root / "plan.json", {"cases": CASES, "budget_seconds": 600, "max_attempts": 48,
                               "assessment": "Whole-artifact manual review; individual semantic misses do not stop the sample"})
    rows, subjects, memories, segments, changes, items = [], [], [], [], [], []
    started = time.monotonic()
    with Mycelium(root / "store", config_path="mycelium.toml", memory_profile="none") as memory:
        write(root / "config.json", asdict(memory.config))
        write(root / "models.json", (await memory.llm.client.list()).model_dump(mode="json"))
        sdk = memory.llm.client
        memory.llm.client = BudgetClient(RecordingClient(sdk, root / "requests"), 600, 48)
        status = "complete"
        try:
            for index, case in enumerate(CASES):
                if index == 2:
                    subjects, memories, segments, changes, items = [], [], [], [], []
                payload = {**case, "existing_subjects": subjects, "prior_memories": memories,
                           "context_segments": segments,
                           "new_subject_ids": [f"new-subject-{index}-{n}" for n in range(20)]}
                write(root / f"{index}-input.json", payload)
                with trace_operation("compact_probe", step=index, stage="retain"):
                    result = await contract.retain(memory.llm, payload)
                write(root / f"{index}-retention.json", result)
                mapped = {s["id"]: s["id"] for s in result["subjects"]}
                smap = {s["id"]: s for s in subjects}
                for s in result["subjects"]:
                    smap[mapped[s["id"]]] = {**s, "id": mapped[s["id"]]}
                subjects = list(smap.values())
                added = [{**m, "id": f"memory-{index}-{m['id']}",
                          "subject_ids": [mapped[s] for s in m["subject_ids"]],
                          "source_time": case["occurred_at"]} for m in result["memories"]]
                memories.extend(added)
                segments.extend(case["segments"])
                changes.extend({**c, "later_id": f"memory-{index}-{c['later_id']}"} for c in result["changes"])
                view_input = {"subjects": subjects, "affected_subject_ids": list(mapped.values()),
                              "memories": memories, "existing_items": items, "pending_changes": changes,
                              "protected_memory_ids": [], "page_exclusions": []}
                write(root / f"{index}-view-input.json", view_input)
                with trace_operation("compact_probe", step=index, stage="present"):
                    view = await contract.present(memory.llm, view_input)
                items = view["items"]
                row = {"step": index, "retention": result, "views": view}
                rows.append(row)
                write(root / "results.json", rows)
                print("STEP", index, len(added), "memories", len(items), "view items", flush=True)
        except (Exception, asyncio.CancelledError) as exc:
            status = "incomplete"
            write(root / "error.json", {"error": f"{type(exc).__name__}: {exc}"})
            raise
        finally:
            await sdk._client.aclose()
            write(root / "completion.json", {"status": status, "seconds": time.monotonic() - started,
                  "steps_completed": len(rows), "metrics": metrics(root), "assessment": "requires_source_review"})
            print("COMPLETE", status, metrics(root), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
