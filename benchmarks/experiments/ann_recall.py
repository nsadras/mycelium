"""Measure ANN recall and latency against exact search over 10k real claim texts."""

import argparse
import asyncio
import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path

import lancedb
import numpy as np
from lancedb.index import IvfFlat

from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.run_tracking import environment_manifest
from mycelium.claim_index import OllamaEmbedder
from mycelium.config import Config


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--distance-type", choices=["l2", "cosine"], default="cosine")
    parser.add_argument("--reuse-vectors", type=Path)
    args = parser.parse_args()
    root = args.resume or fresh_run_root("ann-recall-10k")
    texts = json.loads(args.corpus.read_text())
    if len(texts) != 10000 or len(set(texts)) != 10000:
        raise ValueError(
            "The scale corpus must contain 10k unique complete claim texts"
        )
    config = Config.from_toml(Path("mycelium.toml"))
    embedder = OllamaEmbedder(
        config.llm.url,
        config.retrieval.embedding_model,
        timeout=config.llm.timeout_seconds,
        trace_path=root / "embedding-calls.jsonl",
    )
    digest = await embedder.identity()
    manifest = {
        "config": asdict(config),
        "embedding_digest": digest,
        "corpus_sha256": hashlib.sha256(
            json.dumps(texts, ensure_ascii=False).encode()
        ).hexdigest(),
        "records": len(texts),
        "distance_type": args.distance_type,
        "reused_vectors_from": str(args.reuse_vectors) if args.reuse_vectors else None,
        "query_count": 200,
        "query_seed": 1837,
        "query_kind": "uniform sample of stored claim texts, with production query-task prefix",
        "origin": "unique canonical claim texts from existing local benchmark artifacts",
        "limitations": "Measures vector index recall, not semantic retrieval quality or QA; no new source encoding.",
    }
    if args.resume:
        if json.loads((root / "manifest.json").read_text()) != manifest:
            raise ValueError(
                "ANN experiment resume requires unchanged corpus, configuration and weights"
            )
    else:
        write(root / "manifest.json", manifest)
        write(root / "environment.json", environment_manifest())
        write(root / "claims.json", texts)
        write(root / "models.json", (await embedder.client.list()).model_dump())
    print("OUTPUT", root, flush=True)
    completed = set()
    with await lancedb.connect_async(root / "index") as db:
        table = None
        if args.reuse_vectors and not args.resume:
            original = json.loads((args.reuse_vectors / "manifest.json").read_text())
            for key in [
                "config",
                "embedding_digest",
                "corpus_sha256",
                "query_count",
                "query_seed",
            ]:
                if original[key] != manifest[key]:
                    raise ValueError(f"Reused embeddings have different {key}")
            with await lancedb.connect_async(args.reuse_vectors / "index") as source:
                source_table = await source.open_table("claims")
                table = await db.create_table(
                    "claims", data=await source_table.to_arrow()
                )
            write(
                root / "queries.json",
                json.loads((args.reuse_vectors / "queries.json").read_text()),
            )
        if "claims" in (await db.list_tables()).tables:
            table = await db.open_table("claims")
            completed = {
                row["id"] for row in await table.query().select(["id"]).to_list()
            }
        for start in range(0, len(texts), 64):
            ids = [
                i
                for i in range(start, min(start + 64, len(texts)))
                if i not in completed
            ]
            if ids:
                vectors = await embedder.embed_documents([texts[i] for i in ids])
                if len(vectors) != len(ids) or await embedder.identity() != digest:
                    raise ValueError(
                        "Incomplete embedding response or changed model weights"
                    )
                rows = [{"id": i, "vector": vector} for i, vector in zip(ids, vectors)]
                if table is None:
                    table = await db.create_table("claims", data=rows)
                else:
                    await table.add(rows)
            if start % 512 == 0:
                print("encoded", min(start + 64, len(texts)), flush=True)
        query_ids = (
            np.random.default_rng(1837).choice(len(texts), 200, replace=False).tolist()
        )
        query_path = root / "queries.json"
        if query_path.exists():
            vectors = json.loads(query_path.read_text())["vectors"]
        else:
            vectors = []
            for start in range(0, len(query_ids), 64):
                vectors.extend(
                    await embedder.embed_queries(
                        [texts[i] for i in query_ids[start : start + 64]]
                    )
                )
            if await embedder.identity() != digest:
                raise ValueError("Embedding weights changed while encoding queries")
            write(query_path, {"claim_ids": query_ids, "vectors": vectors})

        async def search(nprobes=None):
            results, times = [], []
            # Warm the table before timed queries.
            await (
                table.query()
                .nearest_to(vectors[0])
                .distance_type(args.distance_type)
                .limit(20)
                .to_list()
            )
            for vector in vectors:
                query = (
                    table.query()
                    .nearest_to(vector)
                    .distance_type(args.distance_type)
                    .limit(20)
                    .select(["id", "_distance"])
                )
                query = (
                    query.bypass_vector_index()
                    if nprobes is None
                    else query.nprobes(nprobes)
                )
                started = time.perf_counter()
                rows = await query.to_list()
                times.append((time.perf_counter() - started) * 1000)
                results.append([row["id"] for row in rows])
            return results, times

        exact, exact_ms = await search()
        write(root / "exact.json", {"results": exact, "latency_ms": exact_ms})
        started = time.perf_counter()
        await table.create_index(
            "vector",
            config=IvfFlat(distance_type=args.distance_type, num_partitions=100),
            replace=True,
        )
        index_seconds = time.perf_counter() - started
        comparisons = []
        for probes in [8, 16, 32, 64, 100]:
            found, latency = await search(probes)
            recalls = [
                len(set(expected) & set(actual)) / 20
                for expected, actual in zip(exact, found)
            ]
            record = {
                "nprobes": probes,
                "recall_at_20": float(np.mean(recalls)),
                "minimum_query_recall": min(recalls),
                "median_ms": float(np.median(latency)),
                "p95_ms": float(np.percentile(latency, 95)),
                "per_query_recall": recalls,
                "latency_ms": latency,
                "results": found,
            }
            comparisons.append(record)
            write(
                root / "results.json",
                {
                    "status": "running",
                    "index_seconds": index_seconds,
                    "comparisons": comparisons,
                },
            )
            print(
                "ANN",
                probes,
                record["recall_at_20"],
                record["median_ms"],
                record["p95_ms"],
                flush=True,
            )
        write(
            root / "results.json",
            {
                "status": "complete",
                "index_seconds": index_seconds,
                "exact_median_ms": float(np.median(exact_ms)),
                "exact_p95_ms": float(np.percentile(exact_ms, 95)),
                "comparisons": comparisons,
            },
        )
        print("COMPLETE", root, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
