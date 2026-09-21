import logging
import os
from openai import AsyncOpenAI
from src.system_design.graph.state import ResearchState

logger = logging.getLogger(__name__)

TURN_RESET = {
    "query_intent": None,
    "intent_confidence": None,
    "intent_reasoning": None,
    "cache_hit": False,
    "sub_questions": [],
    "researched_results": [],
    "final_summary": None,
    "confidence_score": None,
    "confidence_breakdown": None,
}


def format_history(messages: list[dict[str, str]], limit: int = 8, max_chars: int = 800) -> str:
    if not messages:
        return "(no prior turns)"
    lines = []
    for m in messages[-limit:]:
        lines.append(f"{m.get('role', 'user')}: {(m.get('content') or '')[:max_chars]}")
    return "\n".join(lines)


async def contextualize_query_node(state: ResearchState) -> dict:
    logger.info("Entering contextualize node")
    raw_query = state.query
    history = state.messages[:-1]

    if not history:
        return {**TURN_RESET, "standalone_query": raw_query}

    last_topic = (state.last_report or {}).get("query") or "(none)"
    client = AsyncOpenAI(
        base_url=os.getenv("open_router_url"),
        api_key=os.getenv("open_router_api_key"),
    )

    system_instruction = (
        "Rewrite the latest user message as one fully self-contained research question, "
        "resolving pronouns and vague references (it, that, which one, the second point) "
        "using the conversation.\n"
        "Rules:\n"
        "- Do NOT answer the question.\n"
        "- Do NOT copy an earlier answer.\n"
        "- Do NOT add facts that are not in the conversation.\n"
        "- If the message is already self-contained, or is a greeting/thanks/small talk, "
        "return it unchanged.\n"
        "- Keep the user's intent: if they ask a new question about a topic from chat, "
        "write that new question fully, not a request to quote the previous report.\n"
        "- Output only the rewritten message, nothing else."
    )
    user_payload = (
        f"Topic of last research report: {last_topic}\n\n"
        f"Conversation:\n{format_history(history)}\n\n"
        f"Latest user message: {raw_query}"
    )

    try:
        response = await client.chat.completions.create(
            model=os.getenv("llama_chat_model"),
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_payload},
            ],
            temperature=0.0,
            max_tokens=180,
            extra_body={"provider": {"order": ["Groq", "Together"], "allow_fallbacks": True}},
        )
        rewritten = (response.choices[0].message.content or "").strip().strip('"')

        if not rewritten or len(rewritten) > 500:
            rewritten = raw_query
    except Exception as e:
        logger.error("Contextualize failed, using raw query: %s", e)
        rewritten = raw_query

    logger.info("Standalone query: %s", rewritten)
    return {**TURN_RESET, "standalone_query": rewritten}
