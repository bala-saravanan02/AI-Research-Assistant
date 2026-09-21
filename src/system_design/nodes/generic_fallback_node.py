from src.system_design.graph.state import ResearchState
import logging

logger = logging.getLogger(__name__)


async def generic_fallback_response_handler(state: ResearchState) -> dict:
    logger.info("Handling blocked or unsafe request via fallback node")
    error_response = state.final_summary or (
        "We could not complete your request. Please try again with a different question."
    )
    return {"final_summary": error_response}
