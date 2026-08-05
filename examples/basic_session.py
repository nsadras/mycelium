import asyncio
import mycelium

async def main():
    mem = mycelium.Mycelium(
        store_path='./smoke_test_store',
        ollama_model='gemma4:latest',
    )

    # Session 1: record some experience
    async with mem.session(query="what's the system architecture?") as session:
        print("Loaded pages:", [p.slug for p in session.loaded_pages])
        print("Memory context (first 300 chars):", session.memory_context[:300])
        session.record('user', "what's the system architecture?")
        session.record('assistant', "We're using a plain-text wiki backed by a local LLM.")

    # Run dream manually
    report = await mem.dream()
    print("Dream report:", report)

    # Session 2: check that memory was encoded
    async with mem.session(query="what did we decide about storage?") as session:
        print("Loaded pages:", [p.slug for p in session.loaded_pages])
        for p in session.loaded_pages:
            if p.was_flagged:
                print(f"  ⚠ {p.slug} flagged for reconsolidation (score: {p.discrepancy_score:.2f})")

if __name__ == "__main__":
    asyncio.run(main())
