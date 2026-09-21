import logging
import os
import json
from openai import AsyncOpenAI
from src.system_design.graph.state import ResearchState
from src.system_design.utils.confidence import compute_research_confidence
from src.system_design.utils.cache_store import persist_semantic_cache

logger = logging.getLogger(__name__)


def _strip_meta_json(report: str) -> str:
    return report.split("```json", 1)[0].strip()


def collect_sources(results) -> list:
    sources = []
    seen = set()
    for entry in results or []:
        if not isinstance(entry, dict) or entry.get("status") != "success":
            continue
        for item in entry.get("sources") or []:
            if isinstance(item, dict):
                url = (item.get("url") or "").strip()
                title = (item.get("title") or "").strip()
                key = url or title
                payload = {"title": title, "url": url} if url or title else None
            else:
                key = str(item).strip()
                payload = {"title": "", "url": key} if key.startswith("http") else None
            if payload and key and key not in seen:
                seen.add(key)
                sources.append(payload)
    return sources


async def aggregator_node(state: ResearchState) -> dict:
    logger.info("Entering aggregator node to synthesize research results.")

    results = state.researched_results or []
    original_query = state.standalone_query or state.query
    sources = collect_sources(results)

    if not results:
        msg = "No research data was collected to summarize."
        return {
            "final_summary": msg,
            "confidence_score": 0.0,
            "confidence_breakdown": {
                "sub_question_success_rate": 0.0,
                "source_coverage": 0.0,
                "domain_diversity": 0.0,
                "evidence_density": 0.0,
                "llm_calibration": 0.0,
            },
            "messages": [{"role": "assistant", "content": msg}],
        }

    context_chunks = []
    failed_queries = []

    for entry in results:
        if isinstance(entry, dict) and entry.get("status") == "success":
            src_lines = []
            for s in entry.get("sources") or []:
                if isinstance(s, dict) and s.get("url"):
                    src_lines.append(f"- {s.get('title') or s['url']}: {s['url']}")
            src_block = ("\nSources:\n" + "\n".join(src_lines)) if src_lines else ""
            context_chunks.append(
                f"Sub-Question: {entry.get('sub_question')}\nFindings: {entry.get('data')}{src_block}\n---"
            )
        elif isinstance(entry, dict):
            failed_queries.append(f"{entry.get('sub_question')} (Status: {entry.get('status')})")

    if failed_queries:
        logger.warning("Aggregator non-success branches: %s", failed_queries)

    master_context = (
        "\n\n".join(context_chunks)
        if context_chunks
        else "No live tool results available. Do not invent findings."
    )

    last_topic = (state.last_report or {}).get("query") or ""

    client = AsyncOpenAI(
        base_url=os.getenv("open_router_url"),
        api_key=os.getenv("open_router_api_key"),
    )

    system_instruction = (
        "You are a senior research analyst. Write a markdown report that answers the CURRENT "
        "user question using ONLY the collected findings and listed sources.\n"
        "Rules:\n"
        "- Do not invent facts, numbers, or citations.\n"
        "- If findings are thin or conflicting, say so in Limitations.\n"
        "- Do not paste or paraphrase a previous chat report as the answer. Prior chat is "
        "background for entities and constraints only.\n"
        "- Every externally verifiable factual claim must have an inline URL from the collected sources.\n"
        "- Separate **Current evidence** from **Forward-looking implications**. Forecasts must be explicitly "
        "labelled as scenarios/inferences and cite the evidence they are inferred from.\n"
        "- Give the user decision-relevant trade-offs, risks, opportunities, and signals to monitor; do not "
        "inflate certainty.\n"
        "- For a hypothetical or scenario question, reason as a strategic adviser: state the assumptions, "
        "separate evidence from judgment, compare plausible paths, identify second-order effects, and give "
        "a prioritized action plan with triggers for changing course. Never pretend the scenario is a fact.\n"
        "- Structure: executive summary, current evidence, forward-looking implications, limitations, sources.\n"
        "End with JSON in a fenced block ```json ... ``` with keys: "
        "confidence_score (0-1, conservative; lower if few sources), executive_summary."
    )

    user_prompt = (
        f"Primary user query: {original_query}\n"
        f"Prior chat topic (background only): {last_topic or '(none)'}\n"
    )
    user_prompt += f"Collected research findings:\n{master_context}\n\nProduce the report, then the JSON block."

    try:
        response = await client.chat.completions.create(
            model=os.getenv("llama_chat_model"),
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=2200,
            extra_body={
                "provider": {"order": ["Groq", "Together"], "allow_fallbacks": True},
            },
        )

        final_report = response.choices[0].message.content.strip()
        llm_confidence = None
        if "```json" in final_report:
            try:
                json_part = final_report.split("```json", 1)[1].split("```", 1)[0]
                meta = json.loads(json_part.strip())
                llm_confidence = float(meta["confidence_score"])
            except (json.JSONDecodeError, ValueError, IndexError, TypeError):
                pass

        score, breakdown = compute_research_confidence(results, llm_confidence)
        footer = f"\n\n---\n**Report confidence:** {score:.0%} based on {len(sources)} unique source(s)."
        clean_report = _strip_meta_json(final_report) or final_report
        final_with_footer = clean_report + footer
        # Cache only evidence-rich reports; otherwise a weak one-source response
        # could be replayed as an authoritative answer in another conversation.
        if not state.cache_hit and score >= 0.4 and len(sources) >= 2:
            await persist_semantic_cache(
                original_query,
                final_with_footer,
                confidence_score=score,
                sources=sources,
            )

        return {
            "final_summary": final_with_footer,
            "confidence_score": score,
            "confidence_breakdown": breakdown,
            "last_report": {
                "query": original_query,
                "answer": clean_report,
                "sub_questions": state.sub_questions,
                "sources": sources,
                "confidence": score,
            },
            "messages": [{"role": "assistant", "content": clean_report}],
        }

    except Exception as e:
        logger.error("Aggregator synthesis failed: %s", e)
        score, breakdown = compute_research_confidence(results, 0.3)
        fallback_report = (
            f"Here is the raw collected data for your query:\n\n{master_context}\n\n"
            f"(Note: Structural summary generation failed: {e})"
        )
        return {
            "final_summary": fallback_report,
            "confidence_score": score,
            "confidence_breakdown": breakdown,
            "messages": [{"role": "assistant", "content": fallback_report}],
        }
