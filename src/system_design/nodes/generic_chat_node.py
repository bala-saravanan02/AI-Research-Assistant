import os
from openai import AsyncOpenAI
from dotenv import load_dotenv
import logging
from src.system_design.graph.state import ResearchState

logger = logging.getLogger(__name__)
load_dotenv()


def _build_messages(state: ResearchState) -> list[dict[str, str]]:
    system = (
        "You are a helpful, intellectually rigorous research assistant for greetings and small talk. "
        "Use conversation context. Do not invent facts. "
        "If the user is asking for analysis, data, or a new question about a topic, "
        "say you will need to research it rather than quoting an old report as if it were new work. "
        "For harmless hypothetical questions, engage thoughtfully: identify assumptions, trade-offs, "
        "and uncertainty instead of dismissing the scenario."
    )
    out: list[dict[str, str]] = [{"role": "system", "content": system}]
    for m in state.messages[-16:]:
        role = m.get("role", "user")
        if role in ("user", "assistant"):
            out.append({"role": role, "content": m.get("content", "")})
    if not any(m.get("role") == "user" for m in out):
        out.append({"role": "user", "content": state.query})
    elif out[-1]["content"] != state.query:
        out.append({"role": "user", "content": state.query})
    return out


async def generic_chat_conversation(state: ResearchState) -> dict:
    logger.info("Entering generic/follow-up chat node")

    client = AsyncOpenAI(
        base_url=os.getenv("open_router_url"),
        api_key=os.getenv("open_router_api_key"),
    )

    try:
        response = await client.chat.completions.create(
            model=os.getenv("llama_chat_model"),
            messages=_build_messages(state),
            temperature=0.3,
            max_tokens=800,
            extra_body={
                "provider": {"order": ["Groq", "Together"], "allow_fallbacks": True},
            },
        )

        chat_reply = response.choices[0].message.content.strip()
        return {"final_summary": chat_reply}

    except Exception as e:
        logger.error("Generic chat failed: %s", e)
        return {
            "final_summary": f"Chat assistant encountered an error processing this request: {e}",
        }
