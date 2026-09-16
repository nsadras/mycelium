"""Direct bounded grouping and per-group rendering on neutral source statements."""

import asyncio
import json

from benchmarks.experiments.probe_support import fresh_run_root, write
from mycelium import Mycelium
from mycelium.fact_groups import (
    FactText,
    fact_groups_model,
    fact_groups_prompt,
    fact_text_prompt,
)
from mycelium.ontology import entity_type_definition


INVENTORY = [
    "torque wrench",
    "insulated gloves",
    "voltage meter",
    "soldering iron",
    "wire cutters",
    "cable tester",
    "safety glasses",
    "bench clamp",
    "rubber mallet",
    "steel ruler",
    "heat gun",
    "work light",
    "precision screwdriver",
]
CASES = [
    (
        "distinct_memories",
        [
            "The user joined a ceramics class.",
            "The ceramics class meets on Wednesdays.",
            "The user repaired a bicycle on 2031-05-08.",
        ],
        [{0, 1}, {2}],
    ),
    (
        "conditional_commitment",
        [
            "The user will demonstrate the prototype on 2031-05-09 if the safety review is approved.",
            "The safety review for that demonstration is due on 2031-05-06.",
        ],
        [{0, 1}],
    ),
    (
        "bounded_inventory",
        [f"The user's repair workshop has a {item}." for item in INVENTORY],
        None,
    ),
]


async def main():
    root = fresh_run_root("bounded-fact-groups")
    memory = Mycelium(root / "store", config_path="mycelium.toml")
    memory.llm.trace_path = root / "calls.jsonl"
    write(root / "config.json", vars(memory.config.llm))
    write(root / "models.json", (await memory.llm.client.list()).model_dump())
    definition = entity_type_definition("you")
    sections = "\n".join(f"{s.key}: {s.description}" for s in definition.sections)
    owner = "id=you; type=you; title=You"
    results = []
    for trial in range(3):
        for name, statements, scopes in CASES:
            canonical = {
                f"C{i:03d}": {
                    "text": text,
                    "temporal_status": "unknown",
                    "temporal": [],
                    "source_times": [],
                }
                for i, text in enumerate(statements, 1)
            }
            schema = fact_groups_model(canonical, definition.section_keys())
            system, user = fact_groups_prompt(owner, json.dumps(canonical), sections)
            record = {
                "case": name,
                "trial": trial,
                "system": system,
                "user": user,
                "schema": schema.model_json_schema(),
            }
            results.append(record)
            write(root / "results.json", results)
            response = schema.model_validate(
                await memory.llm.call_structured(
                    system,
                    user,
                    schema,
                    num_predict=4096,
                    debug_label="bounded-fact-groups-probe",
                )
            ).model_dump()
            rendered = []
            for group in response["groups"]:
                members = group["member_claim_aliases"]
                if len(members) == 1:
                    text = canonical[members[0]]["text"]
                else:
                    system, user = fact_text_prompt(
                        owner,
                        json.dumps({alias: canonical[alias] for alias in members}),
                    )
                    text = FactText.model_validate(
                        await memory.llm.call_structured(
                            system,
                            user,
                            FactText,
                            num_predict=1024,
                            debug_label="bounded-fact-text-probe",
                        )
                    ).text
                rendered.append({**group, "text": text})
            groups = [
                {int(a[1:]) - 1 for a in g["member_claim_aliases"]} for g in rendered
            ]
            passed = all(len(g) <= 12 for g in groups)
            if scopes is not None:
                passed = passed and all(
                    any(g <= scope for scope in scopes) for g in groups
                )
            if name == "bounded_inventory":
                text = " ".join(g["text"] for g in rendered)
                passed = passed and all(item in text.lower() for item in INVENTORY)
            record.update(response=response, rendered=rendered, passed=passed)
            write(root / "results.json", results)
            print(trial, name, passed, rendered, flush=True)
    print("OUTPUT", root, flush=True)
    if not all(r["passed"] for r in results):
        raise SystemExit("Bounded fact groups failed")


if __name__ == "__main__":
    asyncio.run(main())
