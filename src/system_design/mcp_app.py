import logging
import asyncio
import json
import os
from dotenv import load_dotenv
from fastmcp import FastMCP
from tavily import AsyncTavilyClient
from tavily.errors import UsageLimitExceededError, InvalidAPIKeyError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_server_central")

load_dotenv()

mcp = FastMCP("Centralized Free Research Engine")
tavily_client = AsyncTavilyClient(api_key=os.getenv("TAVILY_API_KEY"))


@mcp.tool(name="brave_web_search")
async def brave_web_search(query: str) -> str:
    """
    Executes a real-time web search via Tavily's API.
    Args:
        query: The search query string passed from the LangGraph thread.
    """
    logger.info(f"[MCP SERVER] Executing Tavily search for: '{query}'")

    try:
        response = await tavily_client.search(
            query,
            max_results=5,
            search_depth="advanced",
            include_answer=False,
        )
        
        results = response.get("results", [])

        if not results:
            logger.warning(f"[MCP SERVER] Tavily returned empty results for: '{query}'")
            return json.dumps({"status": "empty", "data": ""})

        compiled = "\n\n".join(
            f"Title: {r.get('title','')}\nLink: {r.get('url','')}\nSnippet: {r.get('content','')}"
            for r in results
        )
        sources = [
            {"title": r.get("title") or "", "url": r.get("url") or ""}
            for r in results
            if r.get("url")
        ]
        return json.dumps({"status": "ok", "data": compiled, "sources": sources})

    except UsageLimitExceededError as quota_err:
        # Expected, recoverable condition — not a real failure
        logger.warning(f"[MCP SERVER] Tavily quota exceeded: {quota_err}")
        return json.dumps({"status": "quota_exceeded", "data": str(quota_err)})

    except InvalidAPIKeyError as auth_err:
        # Config problem — worth distinguishing from transient errors in logs
        logger.critical(f"[MCP SERVER] Tavily API key invalid: {auth_err}")
        return json.dumps({"status": "error", "data": f"auth failure: {auth_err}"})

    except Exception as err:
        logger.error(f"[MCP SERVER] Tavily search failed: {err}")
        return json.dumps({"status": "error", "data": str(err)})
app = mcp.http_app(transport="sse")


