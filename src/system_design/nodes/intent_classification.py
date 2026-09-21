from src.system_design.graph.state import ResearchState
import os
import logging
import re
from openai import AsyncOpenAI
from dotenv import load_dotenv
import json

load_dotenv()

logger = logging.getLogger(__name__)

INTENTS = (
    "generic_chat",
    "research",
    "follow_up",
    "report_request",
    "clarification_needed",
)

_REPORT_PATTERNS = re.compile(
    r"\b(final report|export|download|pdf|summarize (our|the) (chat|conversation)|write (me )?a report)\b",
    re.I,
)
_FOLLOWUP_PATTERNS = re.compile(
    r"\b(more detail|elaborate|that section|you (said|mentioned|wrote)|previous|above|clarify|"
    r"what did you mean|rephrase|point \d+|the second (one|point))\b",
    re.I,
)
_RESEARCH_HINTS = re.compile(
    r"\b(compare|versus| vs\.? |market|trend|impact|latest|price|regulation|analysis|"
    r"how (does|do|did|can)|what (is|are|was|were)|why (is|are|did|does)|pros|cons|"
    r"should i|forecast|statistics|data|sources?)\b",
    re.I,
)
_SCENARIO_HINTS = re.compile(
    r"\b(what if|if i were|if we were|imagine|hypothetical|scenario|strategy|strategic|"
    r"decision|trade-?off|contingency|would happen)\b",
    re.I,
)


def _heuristic_intent(query: str, has_history: bool, has_prior_research: bool) -> dict | None:
    q = query.strip()
    if len(q) < 3:
        return {"intent": "clarification_needed", "confidence": 0.85, "reasoning": "Query too short."}
    if _REPORT_PATTERNS.search(q):
        return {"intent": "report_request", "confidence": 0.9, "reasoning": "Report/export phrasing detected."}
    if has_history and _FOLLOWUP_PATTERNS.search(q) and not _RESEARCH_HINTS.search(q):
        return {"intent": "follow_up", "confidence": 0.82, "reasoning": "Follow-up phrasing with session history."}
    if _RESEARCH_HINTS.search(q) or _SCENARIO_HINTS.search(q) or len(q.split()) >= 6:
        return None
    return None


def _format_history(messages: list[dict[str, str]], limit: int = 8) -> str:
    if not messages:
        return "(no prior turns)"
    tail = messages[-limit:]
    lines = []
    for m in tail:
        role = m.get("role", "user")
        content = (m.get("content") or "")[:500]
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


async def user_query_intent_classification(state: ResearchState) -> dict:
    logger.info("Entering intent classification")
    raw_query = state.query
    user_query = state.standalone_query or state.query
    history = state.messages[:-1]
    has_history = bool(history)
    last_report = state.last_report
    has_prior = bool(last_report or state.prior_research_context)

    heuristic = _heuristic_intent(raw_query, has_history, has_prior)
    if heuristic and heuristic["confidence"] >= 0.85:
        return {
            "query_intent": heuristic["intent"],
            "intent_confidence": heuristic["confidence"],
            "intent_reasoning": heuristic["reasoning"],
        }

    client = AsyncOpenAI(
        base_url=os.getenv("open_router_url"),
        api_key=os.getenv("open_router_api_key"),
    )

    system_instruction = (
        "You are an intent router for a research assistant.\n"
        "Classify the latest user message into exactly one intent.\n"
        "Return JSON: {\"intent\": \"...\", \"confidence\": 0-1, \"reasoning\": \"short\"}.\n\n"
        "- generic_chat: greetings, thanks, small talk, or chat clearly unrelated to research.\n"
        "- research: any question that needs facts, analysis, comparison, or current information. "
        "If the rewritten standalone version is a complete question about a topic, use research "
        "even if it continues the same subject as the previous chat. Do not classify as follow_up "
        "just because the topic appeared earlier.\n"
        "- follow_up: ONLY when the user is asking about the previous assistant message itself "
        "(what you said, a section of your report, rephrase, clarify your wording). "
        "Not for new facts on the same topic.\n"
        "- report_request: user wants a compiled report/export of this session.\n"
        "- clarification_needed: too vague to act on.\n"
    )

    last_topic = (last_report or {}).get("query") or "(none)"
    user_payload = (
        f"Latest user message (raw):\n{raw_query}\n\n"
        f"Rewritten standalone version:\n{user_query}\n\n"
        f"prior_research_exists: {has_prior}\n"
        f"Topic of last research report: {last_topic}\n\n"
        f"Conversation history:\n{_format_history(history)}\n"
    )

    try:
        response = await client.chat.completions.create(
            model=os.getenv("llama_chat_model"),
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_payload},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=400,
            extra_body={
                "provider": {"order": ["Groq", "Together"], "allow_fallbacks": True},
            },
        )

        raw_output = response.choices[0].message.content.strip()
        parsed = json.loads(raw_output)
        detected = parsed.get("intent", "generic_chat")
        if detected not in INTENTS:
            detected = "research" if _RESEARCH_HINTS.search(user_query) else "generic_chat"

        confidence = float(parsed.get("confidence", 0.6))
        reasoning = str(parsed.get("reasoning", "LLM classification"))

        standalone_is_new_question = (
            user_query.strip().lower() != raw_query.strip().lower()
            and len((user_query or "").split()) >= 6
        )
        if detected == "follow_up" and (_RESEARCH_HINTS.search(user_query) or standalone_is_new_question):
            if not _FOLLOWUP_PATTERNS.search(raw_query):
                detected = "research"
                reasoning += " (overridden: standalone question needs exploration)"

        if detected == "generic_chat" and (_RESEARCH_HINTS.search(user_query) or _SCENARIO_HINTS.search(user_query)) and len(user_query.split()) >= 5:
            detected = "research"
            reasoning += " (overridden: factual research phrasing)"

        return {
            "query_intent": detected,
            "intent_confidence": confidence,
            "intent_reasoning": reasoning,
        }

    except Exception as e:
        logger.error("Intent classifier error: %s", e)
        if _RESEARCH_HINTS.search(user_query) or len((user_query or "").split()) >= 6:
            return {
                "query_intent": "research",
                "intent_confidence": 0.5,
                "intent_reasoning": f"Fallback after error: {e}",
            }
        if has_history and _FOLLOWUP_PATTERNS.search(raw_query):
            return {
                "query_intent": "follow_up",
                "intent_confidence": 0.5,
                "intent_reasoning": f"Fallback after error: {e}",
            }
        return {
            "query_intent": "generic_chat",
            "intent_confidence": 0.4,
            "intent_reasoning": f"Fallback after error: {e}",
        }
