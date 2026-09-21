import json
import logging
import os
from openai import AsyncOpenAI
from src.system_design.graph.state import ResearchState
from src.system_design.utils.confidence import compute_research_confidence

logger = logging.getLogger(__name__)


def _history_text(messages: list[dict[str, str]], limit: int = 20) -> str:
    if not messages:
        return "(empty conversation)"
    lines = []
    for m in messages[-limit:]:
        lines.append(f"{m.get('role', 'user')}: {(m.get('content') or '')[:800]}")
    return "\n".join(lines)


async def report_compiler_node(state: ResearchState) -> dict:
    """Build a final report from chat history and/or prior research without new web search."""
    logger.info("Compiling session report from history and prior research")

    client = AsyncOpenAI(
        base_url=os.getenv("open_router_url"),
        api_key=os.getenv("open_router_api_key"),
    )

    prior = state.prior_research_context or "(no stored research artifact)"
    history = _history_text(state.messages)

    system_instruction = (
        "You produce a final research report from conversation history and prior research notes. "
        "Structure: Executive Summary, Key Findings, Discussion, Limitations, Recommended Next Steps. "
        "End with a JSON block ```json {\"confidence_score\": 0.0-1.0}``` estimating how well "
        "the report is grounded in the supplied material (be conservative)."
    )

    user_prompt = (
        f"User request: {state.query}\n\n"
        f"Conversation:\n{history}\n\n"
        f"Prior research artifact:\n{prior}\n"
    )

    try:
        response = await client.chat.completions.create(
            model=os.getenv("llama_chat_model"),
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=2200,
            extra_body={
                "provider": {"order": ["Groq", "Together"], "allow_fallbacks": True},
            },
        )
        report = response.choices[0].message.content.strip()
        llm_conf = None
        if "```json" in report:
            try:
                block = report.split("```json", 1)[1].split("```", 1)[0]
                llm_conf = float(json.loads(block.strip())["confidence_score"])
            except (json.JSONDecodeError, ValueError, IndexError):
                pass

        results = state.researched_results or []
        if results:
            score, breakdown = compute_research_confidence(results, llm_conf)
        else:
            # A compiled recap has no new independently retrieved evidence. Keep its
            # score explicitly unavailable rather than presenting model self-rating
            # as source-grounded confidence.
            score = None
            breakdown = {
                "source_coverage": 0.0,
                "evidence_density": 0.0,
                "llm_calibration": max(0.0, min(1.0, llm_conf)) if llm_conf is not None else 0.0,
                "confidence_type": "unverified_compilation",
            }

        if score is not None:
            report += f"\n\n---\n**Report confidence:** {score:.0%}"
        return {
            "final_summary": report,
            "confidence_score": score,
            "confidence_breakdown": breakdown,
        }
    except Exception as e:
        logger.error("Report compiler failed: %s", e)
        return {
            "final_summary": f"Could not compile the report: {e}",
            "confidence_score": None,
            "confidence_breakdown": {"error": str(e)},
        }
