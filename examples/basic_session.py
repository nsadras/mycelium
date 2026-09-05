import asyncio
import mycelium

async def main():
    mem = mycelium.Mycelium(
        store_path='./smoke_test_store',
        ollama_model='gemma4:latest',
    )

    # Session 1: record some experience
    async with mem.session(query="what's the system architecture?") as session:
        print("Referenced wiki pages:", [p.slug for p in session.page_references])
        print("Memory context (first 300 chars):", session.memory_context[:300])
        session.record('user', "what's the system architecture?")
        session.record('assistant', "We're using a plain-text wiki backed by a local LLM.")

    # Build captured sources into memory explicitly
    consolidation = await mem.consolidate(mycelium.ConsolidationRequest())
    print("Build Memory report:", consolidation.report)

    # Session 2: check that memory was encoded
    async with mem.session(query="what did we decide about storage?") as session:
        print("Referenced wiki pages:", [p.slug for p in session.page_references])
        for p in session.page_references:
            print(f"  {p.title}: {p.slug} (version {p.version})")

if __name__ == "__main__":
    asyncio.run(main())
