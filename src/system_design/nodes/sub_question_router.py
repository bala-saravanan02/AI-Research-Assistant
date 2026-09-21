from langgraph.constants import Send
import logging 
from src.system_design.graph.state import ResearchState

logger = logging.getLogger(__name__)

def fan_out_router(state:ResearchState):

        sub_questions = state.sub_questions if hasattr(state, "sub_questions") else state.get("sub_questions", [])

        if not sub_questions:
                logger.warning(f"No sub questions is been generated for the user query")
                return []
        return [
        Send(
            "parallel_research_worker", 
            {"sub_question": question}
        ) 
        for question in sub_questions
    ]