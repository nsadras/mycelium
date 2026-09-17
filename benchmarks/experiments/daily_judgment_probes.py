"""Current question-scoped evaluator controls; evaluation calls only."""

import asyncio
from dataclasses import asdict

from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.model_recording import RecordingClient
from benchmarks.suites.daily_driver.eval import judge_probe_answer
from mycelium import Mycelium


CASES = [('concise',
  'What kind of tool does the user want?',
  'A desktop application.',
  'A desktop application that stores gardening notes locally.',
  {'form': 'The user wants a desktop application rather than a website.'},
  ['form'],
  [],
  True,
  True),
 ('similar_wrong',
  'What kind of tool does the user want?',
  'A gardening website.',
  'A desktop application that stores gardening notes locally.',
  {'form': 'The user wants a desktop application rather than a website.'},
  ['form'],
  [],
  True,
  False),
 ('wrong_time',
  'At what time does the call start?',
  '15:00 UTC.',
  '14:00 UTC.',
  {'time': 'The call starts at 14:00 UTC.'},
  ['time'],
  [],
  True,
  False),
 ('right_time',
  'At what time does the call start?',
  'Two in the afternoon, UTC.',
  '14:00 UTC.',
  {'time': 'The call starts at 14:00 UTC.'},
  ['time'],
  [],
  True,
  True),
 ('pending',
  'Is the delivery date settled?',
  'No, the proposed change is still awaiting review.',
  'No, the proposed change is still awaiting review.',
  {},
  [],
  [],
  True,
  True),
 ('pending_wrong',
  'Is the delivery date settled?',
  'Yes, it is settled.',
  'No, the proposed change is still awaiting review.',
  {},
  [],
  [],
  True,
  False),
 ('unrelated',
  'Is the delivery date settled?',
  'The courier has a blue van.',
  'No, the proposed change is still awaiting review.',
  {},
  [],
  [],
  True,
  False),
 ('partial',
  'Who leads the class, and where does it meet?',
  'Amina leads it.',
  'Amina leads the class in Room 4.',
  {},
  [],
  [],
  True,
  False),
 ('unsupported_extra',
  'At what time does the call start?',
  '14:00 UTC; it costs 50 dollars to attend.',
  '14:00 UTC. The evidence says nothing about an attendance fee.',
  {'time': 'The call starts at 14:00 UTC.'},
  ['time'],
  [],
  True,
  False),
 ('refusal',
  'What is the delivery address?',
  'I do not have that information.',
  'The address is unknown.',
  {},
  [],
  [],
  False,
  True),
 ('guess',
  'What is the delivery address?',
  'It might be 7 Park Road.',
  'The address is unknown.',
  {},
  [],
  [],
  False,
  False),
 ('negation',
  'Where should the recording be stored?',
  'Keep it on the computer; do not upload it publicly.',
  'Keep the recording on the computer.',
  {'local': 'Keep the recording on the computer.', 'public': 'Upload the recording publicly.'},
  ['local'],
  ['public'],
  True,
  True),
 ('supported_extra',
  'At what time does the call start?',
  '14:00 UTC, online.',
  'The call is online at 14:00 UTC.',
  {'time': 'The call starts at 14:00 UTC.'},
  ['time'],
  [],
  True,
  True),
 ('unsupported_location',
  'Who leads the class?',
  'Amina, at the downtown studio.',
  'Amina leads the class. Its location is unknown.',
  {},
  [],
  [],
  True,
  False),
 ('unsupported_attribute',
  'What is the lunch menu?',
  'Lentil soup. It is certified gluten-free.',
  'Lentil soup. No dietary certification is specified.',
  {},
  [],
  [],
  True,
  False)]


async def main():
    root = fresh_run_root("daily-judgment-contract")
    print("OUTPUT", root, flush=True)
    with Mycelium(root / "store", config_path="mycelium.toml") as memory:
        memory.llm.client = RecordingClient(memory.llm.client, root / "requests")
        memory.llm.trace_path = root / "calls.jsonl"
        write(root / "config.json", asdict(memory.config))
        write(root / "models.json", (await memory.llm.client.list()).model_dump())
        results = []
        for name, question, answer, reference, facts, required, forbidden, answerable, expected in CASES:
            probe = dict(question=question, expected_answer=reference,
                         required_facts=required, forbidden_facts=forbidden,
                         answerable=answerable)
            judgment = await judge_probe_answer(
                llm=memory.llm, probe=probe, answer=answer,
                gold_facts={key: {"text": value} for key, value in facts.items()},
            )
            record = dict(case=name, probe=probe, answer=answer, facts=facts,
                          judgment=judgment, passed=judgment["passed"] == expected)
            results.append(record)
            write(root / "results.json", results)
            print(name, record["passed"], judgment, flush=True)
        if not all(r["passed"] for r in results):
            raise SystemExit("Daily-driver judgment contract failed")


if __name__ == "__main__":
    asyncio.run(main())
