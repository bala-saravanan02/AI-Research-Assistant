import os
import time
import asyncio
import logging
from typing import Any

from celery import Celery
from celery.result import AsyncResult
from dotenv import load_dotenv

load_dotenv()

from src.system_design.graph.research_graph import compiled_research_graph

logger = logging.getLogger(__name__)

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_instance = Celery("system design tasks", broker=redis_url, backend=redis_url)

celery_instance.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)


def _state_to_dict(final_state: Any) -> dict[str, Any]:
    if isinstance(final_state, dict):
        return final_state
    if hasattr(final_state, "model_dump"):
        return final_state.model_dump()
    return dict(final_state)


async def _persist_run(payload: dict[str, Any], final_state: dict[str, Any], duration_ms: int, status: str) -> None:
    session_id = payload.get("session_id")
    if not session_id:
        return

    from src.system_design.db.database import (
        save_research_run,
        save_message,
        update_session_research_memory,
    )

    user_message_id = payload.get("user_message_id")
    run_id = await save_research_run(
        session_id=session_id,
        message_id=user_message_id,
        query=payload.get("query", ""),
        status=status,
        final_state=final_state,
        duration_ms=duration_ms,
    )

    summary = final_state.get("final_summary") or ""
    intent = final_state.get("query_intent")
    report = final_state.get("last_report") or {}

    prior_text = None
    if report.get("answer"):
        prior_text = report["answer"][:12000]
    elif intent == "report_request" and summary:
        prior_text = summary[:12000]
    if prior_text or (isinstance(report, dict) and report.get("answer")):
        await update_session_research_memory(
            session_id,
            prior_context=prior_text,
            last_report=report if report.get("answer") else None,
        )
    await save_message(
        session_id,
        "assistant",
        summary,
        intent=final_state.get("query_intent"),
        confidence_score=final_state.get("confidence_score"),
        confidence_breakdown=final_state.get("confidence_breakdown"),
        task_id=run_id,
    )


@celery_instance.task(name="execute_langgraph_research", bind=True)
def execute_langgraph_research(self, payload: dict[str, Any]) -> dict:
    query = payload.get("query", "")
    logger.info("Worker starting LangGraph for query: %s", query)
    history = [
        {"role": m.get("role", "user"), "content": m.get("content") or ""}
        for m in (payload.get("messages") or [])
    ][-20:]
    if not history or history[-1]["role"] != "user" or history[-1]["content"] != query:
        history.append({"role": "user", "content": query})

    prior = payload.get("prior_research_context")
    last_report = payload.get("last_report")
    if not last_report and prior:
        last_report = {"query": None, "answer": prior, "sub_questions": [], "sources": []}

    initial_state = {
        "query": query,
        "messages": history,
        "session_id": payload.get("session_id"),
        "user_id": payload.get("user_id"),
        "prior_research_context": prior,
        "last_report": last_report,
        "standalone_query": None,
        "is_safe": True,
        "query_intent": None,
        "cache_hit": False,
        "sub_questions": [],
        "researched_results": [],
        "final_summary": None,
    }

    started = time.perf_counter()
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        
        final_state = loop.run_until_complete(compiled_research_graph.ainvoke(initial_state))
        final_dict = _state_to_dict(final_state)
        duration_ms = int((time.perf_counter() - started) * 1000)

        loop.run_until_complete(_persist_run(payload, final_dict, duration_ms, "success"))

        return {
            "status": "success",
            "processed_prompt": query,
            "standalone_query": final_dict.get("standalone_query"),
            "summary": final_dict.get("final_summary", "No summary compiled"),
            "intent": final_dict.get("query_intent"),
            "intent_confidence": final_dict.get("intent_confidence"),
            "confidence_score": final_dict.get("confidence_score"),
            "confidence_breakdown": final_dict.get("confidence_breakdown"),
            "sources": (final_dict.get("last_report") or {}).get("sources") or [],
            "sub_questions": final_dict.get("sub_questions"),
            "researched_results": final_dict.get("researched_results"),
            "duration_ms": duration_ms,

        }
    except Exception as error:
        duration_ms = int((time.perf_counter() - started) * 1000)
        logger.exception("Worker execution failed")
        failure = {
            "final_summary": f"Worker task exception: {error}",
            "query_intent": None,
            "confidence_score": 0.0,
            "confidence_breakdown": {"error": str(error)},
        }
        try:
            loop.run_until_complete(_persist_run(payload, failure, duration_ms, "failed"))
        except Exception:
            logger.exception("Failed to persist failed run")
        return {
            "status": "failed",
            "processed_prompt": query,
            "summary": failure["final_summary"],
            "duration_ms": duration_ms,
        }


def get_task_result(task_id: str) -> dict[str, Any]:
    result = AsyncResult(task_id, app=celery_instance)
    response: dict[str, Any] = {"task_id": task_id, "state": result.state}
    if result.state == "PENDING":
        response["status"] = "pending"
    elif result.state == "STARTED":
        response["status"] = "running"
    elif result.state == "SUCCESS":
        response["status"] = "success"
        response["result"] = result.result
    elif result.state == "FAILURE":
        response["status"] = "failed"
        response["error"] = str(result.result)
    else:
        response["status"] = result.state.lower()
    return response
