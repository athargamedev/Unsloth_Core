import os
from pathlib import Path
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages

PROJECT_ROOT = Path(__file__).resolve().parents[3]
HISTORY_GUIDE_PRIMER_PATH = PROJECT_ROOT / "subjects" / "reference_docs" / "history_guide_primer.md"
NPC_KEY = "history_guide"
DEFAULT_CATEGORY = "dialogue"

from src.core.tracing.confident_observatory import build_npc_trace_metadata, build_npc_trace_tags
from src.core.tracing.deepeval_tracing import (
    AGENT_METRICS,
    RETRIEVAL_METRICS,
    configure_tracing,
    trace_agent_node,
    trace_retrieval,
    trace_tool,
    trace_type,
)

try:
    from deepeval.tracing import observe, update_current_span, update_current_trace
except Exception:  # pragma: no cover - tracing is optional in local/runtime smoke tests
    observe = None  # type: ignore
    update_current_span = None  # type: ignore
    update_current_trace = None  # type: ignore

try:
    from src.core.vector_db.supabase_pgvector import SupabaseVectorDB, get_embedder
    VECTOR_DB_AVAILABLE = True
except ImportError:
    SupabaseVectorDB = Any  # type: ignore
    VECTOR_DB_AVAILABLE = False


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    dialogue_id: str | None


def build_history_guide_trace_metadata(
    *,
    query: str,
    dialogue_id: str | None,
    model_name: str,
    base_url: str,
) -> dict[str, Any]:
    return build_npc_trace_metadata(
        npc_key=NPC_KEY,
        technique="runtime",
        category=DEFAULT_CATEGORY,
        concept=query[:120],
        turn_type="conversational" if dialogue_id else "single",
        model=model_name,
        extra={
            "dialogue_id": dialogue_id or "",
            "base_url": base_url,
            "runtime": "langgraph_ollama",
        },
    )


def _update_runtime_trace(
    *,
    query: str,
    output: str,
    dialogue_id: str | None,
    model_name: str,
    base_url: str,
) -> None:
    if update_current_trace is None:
        return
    turn_type = "conversational" if dialogue_id else "single"
    update_current_trace(
        name=f"{NPC_KEY}:{DEFAULT_CATEGORY}:{turn_type}",
        input=query,
        output=output,
        thread_id=dialogue_id,
        tags=build_npc_trace_tags(
            npc_key=NPC_KEY,
            technique="runtime",
            category=DEFAULT_CATEGORY,
            turn_type=turn_type,
            environment=os.getenv("UCORE_ENV", "dev"),
        ),
        metadata=build_history_guide_trace_metadata(
            query=query,
            dialogue_id=dialogue_id,
            model_name=model_name,
            base_url=base_url,
        ),
    )


def _get_vector_db() -> SupabaseVectorDB | None:  # type: ignore[name-defined]
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
    if not HISTORY_GUIDE_PRIMER_PATH.exists():
        return "Lore archives not found."

    text = HISTORY_GUIDE_PRIMER_PATH.read_text(encoding="utf-8")
    results = []
    for chunk in text.split("\n\n"):
        if query.lower() in chunk.lower():
            results.append(chunk)

    if results:
        return "\n...\n".join(results)[:1000]
    return "No specific lore found. General knowledge from the archives: " + text[:500]


@trace_retrieval(name="vector_search_lore")
def _search_lore_vector(query: str) -> str:
    """Vector search in Supabase pgvector if available; text search fallback."""
    try:
        db = _get_vector_db()
        if db is None:
            return _search_lore_text(query)

        embedder = get_embedder(backend="ollama")
        docs = db.search(query, embedding_fn=embedder.embed, top_k=5, threshold=0.5)

        if not docs:
            return _search_lore_text(query)

        results = []
        for doc in docs:
            score = doc.similarity_score or 0.0
            results.append(f"[Score: {score:.2f}] {doc.content}")

        return "\n\n".join(results)[:1500]
    except Exception:
        return _search_lore_text(query)


@tool
def search_lore(query: str) -> str:
    """Search the Chronos Spire archives/reference docs for historical lore."""
    with trace_type(name="search_lore", span_type="tool", metrics=RETRIEVAL_METRICS):
        return _search_lore_vector(query)


tools = [search_lore.func]


@trace_agent_node(name="llm_reasoning", metrics=AGENT_METRICS)
def call_model(state: AgentState):
    model_name = os.getenv("LLMUNITY_AGENT_MODEL", "qwen2.5:7b")
    base_url = os.getenv("LLMUNITY_OLLAMA_BASE_URL", "http://localhost:11434")

    model = ChatOllama(model=model_name, base_url=base_url, temperature=0.3)
    model_with_tools = model.bind_tools(tools)

    sys_msg = {
        "role": "system",
        "content": "You are HistoryGuide, a world history storyteller in the Chronos Spire archives. "
        "Use the search_lore tool to look up facts before answering. "
        "Speak exactly 3-5 descriptive sentences. NO markdown formatting, lists, or bullets. "
        "Never present speculation as fact. Always use cause and effect.",
    }

    messages = [sys_msg] + state["messages"]
    response = model_with_tools.invoke(messages)
    if update_current_span is not None:
        update_current_span(
            input=messages,
            output=getattr(response, "content", response),
            metadata={
                "npc_key": NPC_KEY,
                "span_role": "llm_call",
                "model": model_name,
                "base_url": base_url,
                "dialogue_id": state.get("dialogue_id"),
            },
            provider="ollama",
            name="ollama_chat_model",
            metric_collection="llm",
        )
    return {"messages": [response]}


@trace_tool(name="tool_executor", metrics=RETRIEVAL_METRICS)
def tool_node(state: AgentState):
    last_message = state["messages"][-1]

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


workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", tool_node)
workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", should_continue)
workflow.add_edge("tools", "agent")
app = workflow.compile()


def _run_history_guide_traced(query: str, dialogue_id: str | None = None) -> str:
    configure_tracing()
    inputs = {"messages": [HumanMessage(content=query)], "dialogue_id": dialogue_id}
    final_state = app.invoke(inputs)
    output = final_state["messages"][-1].content
    model_name = os.getenv("LLMUNITY_AGENT_MODEL", "qwen2.5:7b")
    base_url = os.getenv("LLMUNITY_OLLAMA_BASE_URL", "http://localhost:11434")
    _update_runtime_trace(
        query=query,
        output=output,
        dialogue_id=dialogue_id,
        model_name=model_name,
        base_url=base_url,
    )
    return output


if observe is not None:
    _run_history_guide_traced = observe(
        type="agent",
        name="npc-runtime:history_guide",
        metric_collection="npc-runtime",
    )(_run_history_guide_traced)


def run_history_guide(query: str, dialogue_id: str | None = None) -> str:
    """Run the history guide and return the final string.

    `dialogue_id` maps to Confident AI `thread_id` for multi-turn Observatory threads.
    """
    return _run_history_guide_traced(query, dialogue_id=dialogue_id)


if __name__ == "__main__":
    print(run_history_guide("Why did Rome fall?"))
