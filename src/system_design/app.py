import os
import json
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

load_dotenv()

from src.system_design.setup.celery_app import celery_instance, get_task_result
from src.system_design.setup.auth import create_access_token, get_current_user_id
from src.system_design.db import database as db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if os.getenv("DATABASE_URL"):
        await db.init_db()
    yield


app = FastAPI(
    title="AI Research Assistant",
    description="LangGraph research assistant with sessions, auth, and task polling",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SessionCreateRequest(BaseModel):
    title: str = "New chat"


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1)


@app.get("/")
async def read_root():
    server_instance = os.getenv("INSTANCE_NAME", "my-own-instance")
    return {
        "status": "healthy",
        "instance_handled_by": server_instance,
        "message": "AI Research Assistant API is healthy",
    }


@app.post("/auth/register")
async def register(payload: RegisterRequest):
    try:
        existing = await db.get_user_by_email(payload.email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        user = await db.create_user(payload.email, payload.password)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Account registration failed")
        raise HTTPException(
            status_code=503,
            detail="Could not create account. The database may be unavailable.",
        ) from None
    token = create_access_token({"sub": str(user["id"]), "email": user["email"]})
    return {"access_token": token, "token_type": "bearer", "user": user}


@app.post("/auth/login")
async def login(payload: LoginRequest):
    try:
        user = await db.get_user_by_email(payload.email)
    except Exception:
        logger.exception("Login lookup failed")
        raise HTTPException(
            status_code=503,
            detail="Could not sign in. The database may be unavailable.",
        ) from None
    if not user or not db.verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": str(user["id"]), "email": user["email"]})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": str(user["id"]), "email": user["email"]},
    }


@app.post("/sessions")
async def create_session(payload: SessionCreateRequest, user_id: str = Depends(get_current_user_id)):
    session = await db.create_session(user_id, payload.title)
    return session


@app.get("/sessions")
async def list_sessions(user_id: str = Depends(get_current_user_id)):
    return await db.list_sessions(user_id)


@app.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str, user_id: str = Depends(get_current_user_id)):
    messages = await db.get_session_messages(session_id, user_id)
    if messages is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return messages


@app.post("/sessions/{session_id}/chat")
async def session_chat(
    session_id: str,
    payload: ChatRequest,
    user_id: str = Depends(get_current_user_id),
):
    prior_messages = await db.get_session_messages(session_id, user_id)
    if prior_messages is None:
        raise HTTPException(status_code=404, detail="Session not found")

    history = [{"role": m["role"], "content": m["content"]} for m in (prior_messages or [])]
    prior_research = await db.get_session_prior_research(session_id)
    last_report = await db.get_session_last_report(session_id)

    user_message_id = await db.save_message(session_id, "user", payload.prompt)

    task_payload = {
        "query": payload.prompt,
        "messages": history,
        "session_id": session_id,
        "user_id": user_id,
        "user_message_id": user_message_id,
        "prior_research_context": prior_research,
        "last_report": last_report,
    }

    async_result = celery_instance.send_task("execute_langgraph_research", args=[task_payload])
    return {
        "status": "accepted",
        "task_id": async_result.id,
        "user_message_id": user_message_id,
        "message": "Research job queued",
    }


@app.post("/research")
async def trigger_research_legacy(payload: ChatRequest):
    """Backward-compatible anonymous research endpoint."""
    task_payload = {"query": payload.prompt, "messages": [], "session_id": None}
    async_result = celery_instance.send_task("execute_langgraph_research", args=[task_payload])
    return {
        "status": "Accepted",
        "task_id": async_result.id,
        "message": "Your research job has been queued.",
    }


@app.get("/tasks/{task_id}")
async def poll_task(task_id: str):
    """Poll Celery task status (used by Streamlit and legacy clients)."""
    return get_task_result(task_id)


@app.get("/dashboard")
async def dashboard(user_id: str = Depends(get_current_user_id)):
    return await db.dashboard_metrics(user_id)


@app.get("/sessions/{session_id}/export")
async def export_session(session_id: str, format: str = "md", user_id: str = Depends(get_current_user_id)):
    messages = await db.get_session_messages(session_id, user_id)
    if messages is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if format == "json":
        content = json.dumps({"session_id": session_id, "messages": messages}, indent=2)
        media = "application/json"
        filename = f"session_{session_id}.json"
    else:
        lines = [f"# Chat export — {session_id}\n"]
        for m in messages:
            conf = m.get("confidence_score")
            suffix = f" (confidence: {conf:.0%})" if conf is not None else ""
            lines.append(f"## {m['role'].title()}{suffix}\n\n{m['content']}\n")
        content = "\n".join(lines)
        media = "text/markdown"
        filename = f"session_{session_id}.md"

    return {
        "filename": filename,
        "media_type": media,
        "content": content,
    }
