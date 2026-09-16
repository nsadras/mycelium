"""Opt-in neutral extraction contract checks using the configured host model."""
import asyncio
import argparse
import json
from dataclasses import asdict
from pathlib import Path

from mycelium.artifacts import SourceSegment
from mycelium.config import Config
from mycelium.encoder import Encoder
from mycelium.ollama import OllamaClient
from mycelium.prompts import claim_extraction_prompt
from mycelium.structured_outputs import extraction_output_model
from mycelium.telemetry import trace_operation
from benchmarks.experiments.probe_support import fresh_run_root, write


CASES = [
    ('conditional_acceptance', 'I can help you repaint the community room on Saturday. Can you bring two brushes?',
     'Yes, I will bring them, provided the delivery arrives by Friday.'),
    ('refusal', 'Would you like to run the pottery workshop next month?',
     'No, I cannot take that on. I may attend as a visitor.'),
    ('unadopted_advice', 'You could start a rooftop garden.', 'Thanks for the suggestion.'),
    ('useful_question', 'How is your week going?',
     'Can you help me prepare for my ceramics exhibition? It opens next Tuesday, and the application is due this Friday.'),
]


async def main(system_suffix: Path | None = None):
    config = Config.from_toml(Path('mycelium.toml')).llm
    root = fresh_run_root('audit-extraction-contract')
    root.mkdir(parents=True)
    write(root/'config.json', asdict(config))
    client = OllamaClient(url=config.url, model=config.model, temperature=config.temperature,
        timeout=config.timeout_seconds, context_window_tokens=config.context_window_tokens,
        top_p=config.top_p, top_k=config.top_k, reasoning_enabled=config.reasoning_enabled,
        reasoning_output_tokens=config.reasoning_output_tokens, reasoning_format=config.reasoning_format,
        trace_path=root/'calls.jsonl')
    results=[]
    for trial in range(3):
        for name, prior_text, reply in CASES:
            prior = SourceSegment('earlier', 0, prior_text, speaker='Morgan', role='assistant', timestamp='2026-06-01T10:00:00')
            current = SourceSegment('new', 0, reply, speaker='Ari', role='user', timestamp='2026-06-01T10:01:00')
            system, user = claim_extraction_prompt('agent_conversation', 'source', ['Ari', 'Morgan'],
                Encoder._render_claim_segments([current]), Encoder._render_segments([prior]))
            if system_suffix:
                system += '\n\n' + system_suffix.read_text().strip()
            schema = extraction_output_model(['new'], ['earlier'])
            sent_schema = schema.model_json_schema()
            with trace_operation('extraction_probe', case=name, trial=trial):
                result = await client.call_structured(system, user, schema, num_predict=8192,
                                                      debug_label='extraction-probe')
            record={'case':name,'trial':trial,'system':system,'user':user,
                    'schema':sent_schema,'response':schema.model_validate(result).model_dump()}
            results.append(record)
            write(root/'results.json', results)
            print(json.dumps({'case':name,'trial':trial,'response':result}), flush=True)
    print('OUTPUT',root,flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-suffix', type=Path)
    args = parser.parse_args()
    asyncio.run(main(args.system_suffix))
