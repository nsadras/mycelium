"""Read-only model provenance for comparing and resuming evaluations."""
import asyncio
from dataclasses import asdict

import httpx

from benchmarks.shared.adapters import OllamaQaClient, MyceliumMemorySystem


def effective_configuration(system) -> dict:
    """Settings captured by the clients, independent of subsequent file edits."""
    result = {}
    qa = getattr(system, 'qa_client', None)
    if isinstance(qa, OllamaQaClient):
        result['qa'] = asdict(qa.config)
    if isinstance(system, MyceliumMemorySystem):
        result['memory'] = asdict(system.config)
    return result


async def model_inventory(system) -> dict:
    qa = getattr(system, 'qa_client', None)
    if not isinstance(qa, OllamaQaClient):
        return {}
    requested = {'qa': (qa.llm.url, qa.model)}
    if isinstance(system, MyceliumMemorySystem):
        requested.update(memory=(system.ollama_url, system.memory_model),
                         embedding=(system.ollama_url, system.config.retrieval.embedding_model))

    async def tags(url):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(url.rstrip('/') + '/api/tags')
                response.raise_for_status()
                return url, response.json()['models'], None
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            return url, [], f'{type(exc).__name__}: {exc}'

    inventories = {url: (models, error) for url, models, error in await asyncio.gather(
        *(tags(url) for url in sorted({url for url, _ in requested.values()}))
    )}
    result = {}
    for role, (url, model) in requested.items():
        models, error = inventories[url]
        qualified = model if ':' in model else model + ':latest'
        match = next((entry for entry in models if entry.get('name') == qualified), None)
        digest = match.get('digest') if match else None
        result[role] = {'url': url, 'model': model, 'digest': digest,
                        'error': error or (None if digest else 'Requested model digest unavailable')}
    return result


def validate_model_resume(previous: dict, current: dict) -> None:
    if previous and previous != current:
        raise ValueError('Model provenance differs from the checkpoint; use a fresh output directory')
