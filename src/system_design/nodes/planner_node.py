from src.system_design.graph.state import ResearchState
import logging
from openai import AsyncOpenAI
import os
import json

logger = logging.getLogger(__name__)


async def planner_decomposition_node(state: ResearchState):
    logger.info("Entering planner node for sub-question preparation")
    prompt = (state.standalone_query or state.query or "").strip()
    last_topic = (state.last_report or {}).get("query") or ""

    client = AsyncOpenAI(
        base_url=os.getenv("open_router_url"),
        api_key=os.getenv("open_router_api_key"),
    )

    system_instruction = (
        "You are an expert research planner.\n"
        "Decompose the user's CURRENT question into 4 to 7 distinct web-search sub-questions.\n"
        "For a scenario or strategic decision, cover the operating context, critical assumptions, "
        "relevant evidence and precedents, options/trade-offs, risks, and leading indicators.\n"
        "Search for this question even if the chat already discussed the topic.\n"
        "Do not create sub-questions that only recap the previous report.\n"
        "Output JSON with key 'sub_questions' as an array of strings."
    )
    user_content = f"Current research request: {prompt}"
    if last_topic:
        user_content += (
            f"\nPrior chat topic (background only, do not substitute for the current request): {last_topic}"
        )

    try:
        response = await client.chat.completions.create(
            model=os.getenv("llama_chat_model"),
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=400,
            extra_body={
                "provider": {"order": ["Groq", "Together"], "allow_fallbacks": True},
            },
        )
        raw_output = response.choices[0].message.content.strip()
        parsed_data = json.loads(raw_output)
        questions_array = parsed_data.get("sub_questions") or [prompt]
        questions_array = [q for q in questions_array if isinstance(q, str) and q.strip()][:7]
        if not questions_array:
            questions_array = [prompt]
        logger.info("Sub-question decomposition completed (%s items)", len(questions_array))
        return {"sub_questions": questions_array}

    except Exception as e:
        logger.error("Planner decomposition failed: %s", e)
        return {"sub_questions": [prompt or state.query]}
