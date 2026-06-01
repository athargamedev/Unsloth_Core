import os
from typing import Annotated, Literal, TypedDict
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.graph import END, StateGraph, START
from langgraph.graph.message import add_messages
from pathlib import Path

# Tracing and observability
from src.core.tracing.deepeval_tracing import (
    configure_tracing,
    trace_agent_node,
    trace_tool,
    trace_retrieval,
    trace_type,
    AGENT_METRICS,
    RETRIEVAL_METRICS,
)

# Vector DB for semantic search (optional; falls back to text search)
try:
    from src.core.vector_db.supabase_pgvector import SupabaseVectorDB, get_embedder, Document
    VECTOR_DB_AVAILABLE = True
except ImportError:
    VECTOR_DB_AVAILABLE = False

# --- Types ---
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    dialogue_id: str = None  # Track multi-turn sessions

# --- Retrieval Functions ---

def _get_vector_db() -> SupabaseVectorDB | None:
    """Try to get Supabase vector DB; return None if not configured."""
    if not VECTOR_DB_AVAILABLE:
        return None
    try:
        return SupabaseVectorDB(table="history_guide_lore")
    except (EnvironmentError, Exception):
        return None


@trace_retrieval(name="text_search_lore")
def _search_lore_text(query: str) -> str:
    """Fallback: simple text search in primer."""
    primer_path = Path(__file__).parents[2] / "subjects" / "reference_docs" / "history_guide_primer.md"
    if not primer_path.exists():
        return "Lore archives not found."
    
    text = primer_path.read_text(encoding="utf-8")
    results = []
    for chunk in text.split("\n\n"):
        if query.lower() in chunk.lower():
            results.append(chunk)
            
    if results:
        return "\n...\n".join(results)[:1000]
    return "No specific lore found. General knowledge from the archives: " + text[:500]


@trace_retrieval(name="vector_search_lore")
def _search_lore_vector(query: str) -> str:
    """Vector search in Supabase pgvector (if available)."""
    try:
        db = _get_vector_db()
        if db is None:
            return _search_lore_text(query)
        
        embedder = get_embedder(backend="ollama")
        docs = db.search(query, embedding_fn=embedder.embed, top_k=5, threshold=0.5)
        
        if not docs:
            return _search_lore_text(query)  # Fallback to text search
        
        # Format retrieved docs
        results = []
        for doc in docs:
            score = doc.similarity_score or 0.0
            results.append(f"[Score: {score:.2f}] {doc.content}")
        
        return "\n\n".join(results)[:1500]
    except Exception as e:
        # Fallback to text search on any error
        return _search_lore_text(query)


@tool
def search_lore(query: str) -> str:
    """Search the Chronos Spire archives (reference docs) for historical lore.
    
    Uses semantic vector search if Supabase is configured; falls back to
    simple text search otherwise.
    """
    # Try vector search first, fall back to text search
    with trace_type(name="search_lore", span_type="tool", metrics=RETRIEVAL_METRICS):
        return _search_lore_vector(query)


tools = [search_lore.func]

# --- Graph Nodes ---

@trace_agent_node(name="llm_reasoning", metrics=AGENT_METRICS)
def call_model(state: AgentState):
    model_name = os.getenv("LLMUNITY_AGENT_MODEL", "qwen2.5:7b")
    base_url = os.getenv("LLMUNITY_OLLAMA_BASE_URL", "http://localhost:11434")
    
    model = ChatOllama(model=model_name, base_url=base_url, temperature=0.3)
    model_with_tools = model.bind_tools(tools)
    
    # System prompt injects the persona
    sys_msg = {
        "role": "system", 
        "content": "You are HistoryGuide, a world history storyteller in the Chronos Spire archives. "
                   "Use the search_lore tool to look up facts before answering. "
                   "Speak exactly 3-5 descriptive sentences. NO markdown formatting, lists, or bullets. "
                   "Never present speculation as fact. Always use cause and effect."
    }
    
    messages = [sys_msg] + state["messages"]
    response = model_with_tools.invoke(messages)
    return {"messages": [response]}

@trace_tool(name="tool_executor", metrics=RETRIEVAL_METRICS)
def tool_node(state: AgentState):
    last_message = state["messages"][-1]
    
    # Execute tools
    results = []
    for tool_call in last_message.tool_calls:
        if tool_call["name"] == "search_lore":
            res = search_lore.invoke(tool_call["args"])
            results.append(
                ToolMessage(content=str(res), name=tool_call["name"], tool_call_id=tool_call["id"])
            )
    return {"messages": results}

def should_continue(state: AgentState) -> Literal["tools", "__end__"]:
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return "__end__"

# --- Build Graph ---
workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", tool_node)

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", should_continue)
workflow.add_edge("tools", "agent")

app = workflow.compile()

def run_history_guide(query: str) -> str:
    """Helper to run the agent and return just the final string."""
    configure_tracing()
    inputs = {"messages": [HumanMessage(content=query)]}
    final_state = app.invoke(inputs)
    return final_state["messages"][-1].content

if __name__ == "__main__":
    print(run_history_guide("Why did Rome fall?"))
