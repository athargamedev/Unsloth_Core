import os
from typing import Any

from langchain_ollama import ChatOllama

from src.core.tracing.confident_observatory import build_npc_trace_metadata, build_npc_trace_tags
from src.core.tracing.deepeval_tracing import configure_tracing

try:
    from deepeval.tracing import observe, update_current_span, update_current_trace
except Exception:  # pragma: no cover - tracing is optional in local/runtime smoke tests
    observe = None  # type: ignore
    update_current_span = None  # type: ignore
    update_current_trace = None  # type: ignore

NPC_KEY = "chef_assistant"
DEFAULT_CATEGORY = "dialogue"


def build_chef_assistant_trace_metadata(
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
            "runtime": "direct_ollama",
        },
    )


def _system_prompt() -> str:
    return (
        "You are ChefAssistant, a safe, practical cooking assistant for a Unity NPC. "
        "Answer with calm, specific kitchen guidance. Mention food safety when relevant. "
        "Keep responses to 1-3 short sentences. NO markdown formatting, lists, or bullets. "
        "Do not provide medical diets, eating-disorder advice, or unsafe food shortcuts."
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
        metadata=build_chef_assistant_trace_metadata(
            query=query,
            dialogue_id=dialogue_id,
            model_name=model_name,
            base_url=base_url,
        ),
    )


def _run_chef_assistant_traced(query: str, dialogue_id: str | None = None) -> str:
    configure_tracing()
    model_name = os.getenv("LLMUNITY_AGENT_MODEL", "qwen2.5:7b")
    base_url = os.getenv("LLMUNITY_OLLAMA_BASE_URL", "http://localhost:11434")
    messages = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": query},
    ]
    model = ChatOllama(model=model_name, base_url=base_url, temperature=0.2)
    response = model.invoke(messages)
    output = str(getattr(response, "content", response))
    if update_current_span is not None:
        update_current_span(
            input=messages,
            output=output,
            metadata={
                "npc_key": NPC_KEY,
                "span_role": "llm_call",
                "model": model_name,
                "base_url": base_url,
                "dialogue_id": dialogue_id,
            },
            provider="ollama",
            name="ollama_chat_model",
            metric_collection="llm",
        )
    _update_runtime_trace(
        query=query,
        output=output,
        dialogue_id=dialogue_id,
        model_name=model_name,
        base_url=base_url,
    )
    return output


if observe is not None:
    _run_chef_assistant_traced = observe(
        type="agent",
        name="npc-runtime:chef_assistant",
        metric_collection="npc-runtime",
    )(_run_chef_assistant_traced)


def run_chef_assistant(query: str, dialogue_id: str | None = None) -> str:
    """Run ChefAssistant and map dialogue_id to Confident AI thread_id."""
    return _run_chef_assistant_traced(query, dialogue_id=dialogue_id)


if __name__ == "__main__":
    print(run_chef_assistant("How do I dice an onion safely?"))
