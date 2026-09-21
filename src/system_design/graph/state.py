from typing import Any, List, Dict, Optional
from pydantic import BaseModel, Field
import operator
from typing import Annotated, Any, List, Dict, Optional

class ChatMessage(BaseModel):
    role: str = Field(description="user | assistant | system")
    content: str = Field(default="")


class ResearchState(BaseModel):
    query: str = Field(description="The primary raw user search query string.")
    messages: Annotated[List[Dict[str, str]], operator.add] = Field(   # CHANGED
        default_factory=list,
        description="Conversation history for multi-turn chat.",
    )
    standalone_query: Optional[str] = Field(
        default=None, description="Follow-up rewritten as a self-contained question."
    )
    last_report: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Most recent research result: {query, answer, sub_questions, sources, confidence}.",
    )
    
    session_id: Optional[str] = Field(default=None, description="Chat session identifier.")
    user_id: Optional[str] = Field(default=None, description="Authenticated user identifier.")

    is_safe: bool = Field(default=True, description="Guardrail flag marking prompt safety status.")
    query_intent: Optional[str] = Field(default=None, description="Classified intent payload.")
    intent_confidence: Optional[float] = Field(default=None, description="Intent classifier confidence.")
    intent_reasoning: Optional[str] = Field(default=None, description="Short intent classification rationale.")

    cache_hit: bool = Field(default=False, description="Flag indicating if summary was pulled from cache.")
    prior_research_context: Optional[str] = Field(
        default=None,
        description="Prior research report or findings injected from session storage.",
    )

    sub_questions: List[str] = Field(default_factory=list, description="Array of split research tasks.")
    researched_results: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Compiled outcomes from research.",
    )

    final_summary: Optional[str] = Field(default=None, description="The complete synthesized technical brief.")
    confidence_score: Optional[float] = Field(
        default=None,
        description="Overall report confidence score in [0, 1].",
    )
    confidence_breakdown: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Explainable confidence components.",
    )
    report_format: str = Field(default="markdown", description="markdown | json structured hint for UI.")
