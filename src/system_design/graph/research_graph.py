from langgraph.graph import StateGraph, START, END
from src.system_design.graph.state import ResearchState
from src.system_design.nodes.input_guardrail import input_guardrail_checker
from src.system_design.nodes.generic_fallback_node import generic_fallback_response_handler
from src.system_design.nodes.intent_classification import user_query_intent_classification
from src.system_design.nodes.generic_chat_node import generic_chat_conversation
from src.system_design.nodes.cache_node import semantic_cache_check_node
from src.system_design.nodes.planner_node import planner_decomposition_node
from src.system_design.nodes.batch_researcher import batch_research_node
from src.system_design.nodes.aggregator import aggregator_node
from src.system_design.nodes.report_compiler_node import report_compiler_node
from src.system_design.nodes.contextualize_node import contextualize_query_node
from src.system_design.nodes.followup_node import research_followup_node
from langgraph.checkpoint.memory import MemorySaver

import logging

logger = logging.getLogger(__name__)

workflow = StateGraph(ResearchState)


def routing_condition(state: ResearchState):
    if state.is_safe:
        return "proceed_to_success"
    return "go_to_fallback"


def intent_routing_condition(state):
    intent = state.query_intent or "generic_chat"
    if intent == "research":          return "route_to_research"
    if intent == "report_request":    return "route_to_report"
    if intent == "follow_up":         return "route_to_followup"
    return "general_chat"


def user_query_routing_cache(state: ResearchState):
    if state.cache_hit:
        return "return_through_cache"
    return "go_for_planner"


def research_node_entry_gateway(state: ResearchState) -> dict:
    logger.info("Entering research branch gateway")
    return {}


workflow.add_node("input_guardrail_node", input_guardrail_checker)
workflow.add_node("intent_classifier_node", user_query_intent_classification)
workflow.add_node("contextualize_node", contextualize_query_node)   # NEW
workflow.add_node("followup_node", research_followup_node) 
workflow.add_node("research_node", research_node_entry_gateway)
workflow.add_node("semantic_cache_node", semantic_cache_check_node)
workflow.add_node("planner_node", planner_decomposition_node)
workflow.add_node("batch_research_node", batch_research_node)
workflow.add_node("aggregator_node", aggregator_node)
workflow.add_node("report_compiler_node", report_compiler_node)
workflow.add_node("generic_chat_node", generic_chat_conversation)
workflow.add_node("general_fallback_node", generic_fallback_response_handler)

workflow.add_edge(START, "input_guardrail_node")
workflow.add_conditional_edges(
    "input_guardrail_node", routing_condition,
    {"proceed_to_success": "contextualize_node",                    # was intent_classifier_node
     "go_to_fallback": "general_fallback_node"},
)
workflow.add_edge("contextualize_node", "intent_classifier_node")

workflow.add_conditional_edges(
    "intent_classifier_node", intent_routing_condition,
    {"route_to_research": "research_node",
     "route_to_report": "report_compiler_node",
     "route_to_followup": "followup_node",                          # NEW
     "general_chat": "generic_chat_node"},
)
workflow.add_conditional_edges(
    "followup_node",
    lambda s: "needs_research" if s.query_intent == "research" else "answered",
    {"answered": END, "needs_research": "research_node"},
)

workflow.add_edge("research_node", "semantic_cache_node")
workflow.add_conditional_edges(
    "semantic_cache_node",
    user_query_routing_cache,
    {
        "return_through_cache": END,
        "go_for_planner": "planner_node",
    },
)
workflow.add_edge("planner_node", "batch_research_node")
workflow.add_edge("batch_research_node", "aggregator_node")
workflow.add_edge("aggregator_node", END)
workflow.add_edge("report_compiler_node", END)
workflow.add_edge("generic_chat_node", END)
workflow.add_edge("general_fallback_node", END)


compiled_research_graph = workflow.compile()
logger.info("Research graph compiled successfully")
