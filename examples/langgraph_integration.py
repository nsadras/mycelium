from langgraph.graph import StateGraph
from typing import TypedDict
import mycelium

class AgentState(TypedDict):
    input: str
    output: str
    session_id: str
    memory_context: str

mem = mycelium.Mycelium(
    store_path='./store',
    ollama_model='gemma3:12b'
)

async def memory_node(state: AgentState) -> AgentState:
    """Load relevant memory into agent state."""
    # We load pages without starting a full session just for context
    pages = await mem.load_context(query=state['input'])
    
    # We can format the pages manually if we aren't using the session context manager
    blocks = []
    for page in pages:
        header = f"=== MEMORY: {page.title} (confidence: {page.confidence:.2f}, v{page.version}) ==="
        blocks.append(f"{header}\n{page.content}")
        
    state['memory_context'] = "\n\n".join(blocks) + "\n\n=== END MEMORY ===" if blocks else ""
    return state

async def record_node(state: AgentState) -> AgentState:
    """Record session output to episodic log."""
    await mem.encoder.encode_session(
        transcript=f"USER: {state['input']}\nASSISTANT: {state['output']}",
        session_id=state['session_id'],
        source_type="agent_conversation",
    )
    return state

async def generate_node(state: AgentState) -> AgentState:
    """Mock generation node."""
    # In a real app, you would pass state['memory_context'] + state['input'] to an LLM
    print(f"Context loaded:\n{state['memory_context']}")
    print(f"Input: {state['input']}")
    
    state['output'] = "I am a mock response based on memory."
    return state

def setup_graph():
    graph = StateGraph(AgentState)
    graph.add_node('load_memory', memory_node)
    graph.add_node('generate', generate_node)
    graph.add_node('record_memory', record_node)
    
    graph.set_entry_point('load_memory')
    graph.add_edge('load_memory', 'generate')
    graph.add_edge('generate', 'record_memory')
    
    return graph.compile()

async def main():
    app = setup_graph()
    state = {
        "input": "What is our architecture?",
        "session_id": "ses-langgraph-1",
        "output": "",
        "memory_context": ""
    }
    
    # Note: langgraph async execution would use ainvoke
    # This is just a conceptual example.
    result = await app.ainvoke(state)
    print("Final Output:", result['output'])

if __name__ == "__main__":
    # Note: running this requires langgraph to be installed
    # asyncio.run(main())
    pass
