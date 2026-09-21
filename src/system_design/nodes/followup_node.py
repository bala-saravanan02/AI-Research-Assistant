import json
import logging
import os
import re
from openai import AsyncOpenAI
from src.system_design.graph.state import ResearchState

logger = logging.getLogger(__name__)

MAX_CONTEXT_CHARS = 12000

_META_FOLLOWUP = re.compile(
    r"\b(what did you (say|mean|write)|rephrase|your (last )?(point|section|answer|report)|"
    r"summarize what you (said|wrote)|which (point|section)|you (said|mentioned|wrote))\b",
    re.I,
)


def _escalate(reason: str) -> dict:
    logger.info("Follow-up escalating to research: %s", reason)
    return {
        "query_intent": "research",
        "intent_reasoning": f"Escalated from follow_up: {reason}",
    }


def _followup_confidence(report: dict, source_count: int) -> tuple[float | None, dict]:
    """Confidence for an explanation of existing evidence, never a made-up default."""
    if source_count == 0:
        return None, {"confidence_type": "grounded_followup", "source_coverage": 0.0}
    try:
        inherited = float(report.get("confidence"))
    except (TypeError, ValueError):
        inherited = 0.0
    coverage = min(1.0, source_count / 6.0)
    score = round(min(1.0, 0.6 * inherited + 0.4 * coverage), 3)
    return score, {
        "confidence_type": "grounded_followup",
        "inherited_report_confidence": round(inherited, 3),
        "source_coverage": round(coverage, 3),
    }


async def research_followup_node(state: ResearchState) -> dict:
    """Resolve chat references, then research unless the user is asking about the prior answer itself."""
    logger.info("Entering follow-up node")
    question = state.standalone_query or state.query
    raw = state.query or ""

    report = state.last_report or {}
    has_prior = bool(report.get("answer") or state.prior_research_context)
    if not has_prior:
        return _escalate("no prior research to ground a follow-up")

    looks_like_meta = bool(_META_FOLLOWUP.search(raw))
    if not looks_like_meta:
        return _escalate("new or expanded question — searching instead of quoting prior chat")

    if report.get("answer"):
        sources = report.get("sources") or []
        context = f"Previous research report:\n{report['answer'][:MAX_CONTEXT_CHARS]}"
        if sources:
            context += f"\n\nSources used: {sources}"
    else:
        context = f"Previous research:\n{(state.prior_research_context or '')[:MAX_CONTEXT_CHARS]}"

    client = AsyncOpenAI(
        base_url=os.getenv("open_router_url"),
        api_key=os.getenv("open_router_api_key"),
    )

    system_instruction = (
        "You handle a follow-up about the assistant's previous answer.\n"
        "Return JSON with keys: can_answer (bool), needs_research (bool), answer (markdown).\n"
        "- can_answer=true only if the user is asking what was already stated "
        "(rephrase, locate a section, explain a term already defined in the report).\n"
        "- If they want more facts, newer data, another entity, a comparison, or depth "
        "the report does not contain, set needs_research=true and can_answer=false.\n"
        "- Answer the user's specific question directly and explain the relevant idea in plain language. "
        "Do not paste the whole prior report or lead with a recap unless explicitly requested.\n"
        "- Never invent facts."
    )
    user_payload = f"{context}\n\nFollow-up question: {question}\nOriginal wording: {raw}"

    try:
        response = await client.chat.completions.create(
            model=os.getenv("llama_chat_model"),
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_payload},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=1200,
            extra_body={"provider": {"order": ["Groq", "Together"], "allow_fallbacks": True}},
        )
        parsed = json.loads(response.choices[0].message.content.strip())
    except Exception as e:
        return _escalate(f"follow-up LLM/parse error: {e}")

    if parsed.get("needs_research") or not parsed.get("can_answer"):
        return _escalate("context insufficient — exploring the question")

    answer = (parsed.get("answer") or "").strip()
    if not answer:
        return _escalate("empty follow-up answer")

    score, breakdown = _followup_confidence(report, len(report.get("sources") or []))

    return {
        "final_summary": answer,
        "confidence_score": score,
        "confidence_breakdown": breakdown,
        "messages": [{"role": "assistant", "content": answer}],
    }
