import logging

from src.system_design.graph.state import ResearchState
from src.system_design.utils.cache_store import lookup_semantic_cache

logger = logging.getLogger(__name__)


async def semantic_cache_check_node(state: ResearchState) -> dict:
    logger.info("Entering semantic vector lookup")
    standalone = state.standalone_query or state.query
    hit = await lookup_semantic_cache(standalone)
    if not hit.get("cache_hit"):
        return {"cache_hit": False}

    cached_report = hit.get("last_report") or {}
    cached_q = (cached_report.get("query") or "").lower().strip()
    last_q = ((state.last_report or {}).get("query") or "").lower().strip()
    standalone_n = (standalone or "").lower().strip()
    if last_q and cached_q == last_q and standalone_n != last_q:
        logger.info("Skipping cache hit that would replay the previous chat report")
        return {"cache_hit": False}

    cached_report["query"] = standalone
    hit.pop("_cache_meta", None)
    breakdown = hit.get("confidence_breakdown") or {}
    breakdown["source"] = "semantic_cache_hit"
    hit["confidence_breakdown"] = breakdown
    hit["last_report"] = cached_report
    return hit
