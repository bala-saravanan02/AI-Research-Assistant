# AI Research Assistant (LangGraph)

Multi-agent research pipeline with guardrails, hybrid intent routing, MCP web search, semantic caching (pgvector), Celery workers, and a Streamlit chat UI with login, sessions, confidence scores, and exports.

## Architecture

- **FastAPI** (×2 behind **Nginx**): auth, sessions, chat, task polling, dashboard, export
- **Celery workers**: run compiled LangGraph graph
- **Postgres + pgvector**: users, messages, research runs, semantic cache
- **Redis**: Celery broker/backend
- **MCP server**: Tavily search tool exposed over SSE
- **Streamlit**: login, sidebar sessions, chat, downloads, analytics

## LangGraph flow

`guardrail → intent (research | report | chat) → research branch (cache → planner → batch MCP → aggregator)` or `report_compiler` / `generic_chat`.

## Quick start (Docker)

1. Copy `.env` and set `open_router_*`, `TAVILY_API_KEY`, `JWT_SECRET_KEY`.
2. `docker compose up --build`
3. API: http://localhost/research (legacy) or use Streamlit: http://localhost:8501

## Local Streamlit (API already running)

```bash
uv sync
set API_BASE_URL=http://localhost:80
uv run streamlit run src/system_design/streamlit_app.py
```

## Interview highlights

- Explainable **confidence breakdown** on research reports
- **Hybrid intent router** (heuristics + structured LLM + session context)
- **Session memory** and **final report** path without redundant web search
- Resilience: circuit breaker, semaphores, graceful MCP fallbacks
- Horizontal scale: dual API + dual workers + load balancer
