import os
import json
import logging
import asyncio
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse
from uuid import UUID, uuid4

import asyncpg
import bcrypt

logger = logging.getLogger(__name__)


def _serialize(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def row_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    return {k: _serialize(v) for k, v in dict(row).items()}


async def get_connection() -> asyncpg.Connection:
    last_error: Exception | None = None
    for db_url in _candidate_db_urls():
        try:
            return await asyncpg.connect(db_url)
        except Exception as exc:
            last_error = exc
            logger.warning("Database connection failed for %s: %s", _redact_db_url(db_url), exc)
    if last_error:
        raise RuntimeError(f"DATABASE_URL is not reachable: {last_error}") from last_error
    raise RuntimeError("DATABASE_URL is not configured")


def _candidate_db_urls() -> list[str]:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        return []
    urls = [db_url]
    parsed = urlparse(db_url)
    if parsed.hostname in {"research-vector-db"}:
        port = parsed.port or 5432
        auth = ""
        if parsed.username:
            auth = parsed.username
            if parsed.password:
                auth += f":{parsed.password}"
            auth += "@"
        local = parsed._replace(netloc=f"{auth}127.0.0.1:{port}")
        urls.append(urlunparse(local))
    return urls


def _redact_db_url(db_url: str) -> str:
    parsed = urlparse(db_url)
    host = parsed.hostname or ""
    return f"{parsed.scheme}://{host}{parsed.path}"


async def init_db(retries: int = 10, delay_seconds: float = 2.0) -> None:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            await _init_db_once()
            return
        except Exception as exc:
            last_error = exc
            logger.warning("Database init attempt %s/%s failed: %s", attempt, retries, exc)
            await asyncio.sleep(delay_seconds)
    raise RuntimeError(f"Could not initialize database: {last_error}") from last_error


async def _init_db_once() -> None:
    conn = await get_connection()
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id UUID PRIMARY KEY,
                user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL DEFAULT 'New chat',
                prior_research_context TEXT,
                last_report JSONB,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        )
        await conn.execute(
            "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS last_report JSONB;"
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id UUID PRIMARY KEY,
                session_id UUID REFERENCES chat_sessions(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                intent TEXT,
                confidence_score DOUBLE PRECISION,
                confidence_breakdown JSONB,
                task_id TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS research_runs (
                id UUID PRIMARY KEY,
                session_id UUID REFERENCES chat_sessions(id) ON DELETE SET NULL,
                message_id UUID REFERENCES messages(id) ON DELETE SET NULL,
                query TEXT NOT NULL,
                status TEXT NOT NULL,
                sub_questions JSONB,
                researched_results JSONB,
                final_summary TEXT,
                confidence_score DOUBLE PRECISION,
                confidence_breakdown JSONB,
                intent TEXT,
                duration_ms INTEGER,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        )
        logger.info("Database schema initialized")
    finally:
        await conn.close()


def hash_password(password: str) -> str:
    payload = password.encode("utf-8")[:72]
    return bcrypt.hashpw(payload, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    payload = password.encode("utf-8")[:72]
    try:
        return bcrypt.checkpw(payload, password_hash.encode("utf-8"))
    except ValueError:
        return False


async def create_user(email: str, password: str) -> dict[str, Any]:
    user_id = str(uuid4())
    conn = await get_connection()
    try:
        await conn.execute(
            "INSERT INTO users (id, email, password_hash) VALUES ($1, $2, $3)",
            user_id,
            email.lower().strip(),
            hash_password(password),
        )
        return {"id": user_id, "email": email.lower().strip()}
    finally:
        await conn.close()


async def get_user_by_email(email: str) -> Optional[asyncpg.Record]:
    conn = await get_connection()
    try:
        return await conn.fetchrow(
            "SELECT id, email, password_hash FROM users WHERE email = $1",
            email.lower().strip(),
        )
    finally:
        await conn.close()


async def create_session(user_id: str, title: str = "New chat") -> dict[str, Any]:
    session_id = str(uuid4())
    conn = await get_connection()
    try:
        await conn.execute(
            "INSERT INTO chat_sessions (id, user_id, title) VALUES ($1, $2, $3)",
            session_id,
            user_id,
            title,
        )
        return {"id": session_id, "title": title}
    finally:
        await conn.close()


async def list_sessions(user_id: str) -> list[dict[str, Any]]:
    conn = await get_connection()
    try:
        rows = await conn.fetch(
            """
            SELECT id, title, created_at, updated_at
            FROM chat_sessions
            WHERE user_id = $1
            ORDER BY updated_at DESC
            """,
            user_id,
        )
        return [row_to_dict(r) for r in rows]
    finally:
        await conn.close()


async def get_session_messages(session_id: str, user_id: str) -> list[dict[str, Any]] | None:
    conn = await get_connection()
    try:
        owned = await conn.fetchval(
            "SELECT 1 FROM chat_sessions WHERE id = $1 AND user_id = $2",
            session_id,
            user_id,
        )
        if not owned:
            return None
        rows = await conn.fetch(
            """
            SELECT role, content, intent, confidence_score, created_at
            FROM messages
            WHERE session_id = $1
            ORDER BY created_at ASC
            """,
            session_id,
        )
        return [row_to_dict(r) for r in rows]
    finally:
        await conn.close()


async def get_session_prior_research(session_id: str) -> Optional[str]:
    conn = await get_connection()
    try:
        return await conn.fetchval(
            "SELECT prior_research_context FROM chat_sessions WHERE id = $1",
            session_id,
        )
    finally:
        await conn.close()


async def get_session_last_report(session_id: str) -> Optional[dict[str, Any]]:
    conn = await get_connection()
    try:
        value = await conn.fetchval(
            "SELECT last_report FROM chat_sessions WHERE id = $1",
            session_id,
        )
        if value is None:
            return None
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return None
        if isinstance(value, dict):
            return value
        return None
    finally:
        await conn.close()


async def touch_session(session_id: str) -> None:
    conn = await get_connection()
    try:
        await conn.execute(
            "UPDATE chat_sessions SET updated_at = NOW() WHERE id = $1",
            session_id,
        )
    finally:
        await conn.close()


async def save_message(
    session_id: str,
    role: str,
    content: str,
    *,
    intent: str | None = None,
    confidence_score: float | None = None,
    confidence_breakdown: dict | None = None,
    task_id: str | None = None,
) -> str:
    message_id = str(uuid4())
    conn = await get_connection()
    try:
        await conn.execute(
            """
            INSERT INTO messages (
                id, session_id, role, content, intent, confidence_score,
                confidence_breakdown, task_id
            ) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
            """,
            message_id,
            session_id,
            role,
            content,
            intent,
            confidence_score,
            json.dumps(confidence_breakdown) if confidence_breakdown else None,
            task_id,
        )
        await conn.execute(
            "UPDATE chat_sessions SET updated_at = NOW() WHERE id = $1",
            session_id,
        )
        return message_id
    finally:
        await conn.close()


async def update_session_prior_research(session_id: str, context: str) -> None:
    conn = await get_connection()
    try:
        await conn.execute(
            "UPDATE chat_sessions SET prior_research_context = $1, updated_at = NOW() WHERE id = $2",
            context,
            session_id,
        )
    finally:
        await conn.close()


async def update_session_research_memory(
    session_id: str,
    *,
    prior_context: str | None = None,
    last_report: dict[str, Any] | None = None,
) -> None:
    conn = await get_connection()
    try:
        if prior_context is not None and last_report is not None:
            await conn.execute(
                """
                UPDATE chat_sessions
                SET prior_research_context = $1, last_report = $2::jsonb, updated_at = NOW()
                WHERE id = $3
                """,
                prior_context,
                json.dumps(last_report),
                session_id,
            )
        elif last_report is not None:
            await conn.execute(
                """
                UPDATE chat_sessions
                SET last_report = $1::jsonb, updated_at = NOW()
                WHERE id = $2
                """,
                json.dumps(last_report),
                session_id,
            )
        elif prior_context is not None:
            await conn.execute(
                """
                UPDATE chat_sessions
                SET prior_research_context = $1, updated_at = NOW()
                WHERE id = $2
                """,
                prior_context,
                session_id,
            )
    finally:
        await conn.close()


async def save_research_run(
    *,
    session_id: str | None,
    message_id: str | None,
    query: str,
    status: str,
    final_state: dict[str, Any],
    duration_ms: int,
) -> str:
    run_id = str(uuid4())
    conn = await get_connection()
    try:
        await conn.execute(
            """
            INSERT INTO research_runs (
                id, session_id, message_id, query, status,
                sub_questions, researched_results, final_summary,
                confidence_score, confidence_breakdown, intent, duration_ms
            ) VALUES (
                $1, $2, $3, $4, $5,
                $6::jsonb, $7::jsonb, $8,
                $9, $10::jsonb, $11, $12
            )
            """,
            run_id,
            session_id,
            message_id,
            query,
            status,
            json.dumps(final_state.get("sub_questions") or []),
            json.dumps(final_state.get("researched_results") or []),
            final_state.get("final_summary"),
            final_state.get("confidence_score"),
            json.dumps(final_state.get("confidence_breakdown") or {}),
            final_state.get("query_intent"),
            duration_ms,
        )
        return run_id
    finally:
        await conn.close()


async def dashboard_metrics(user_id: str) -> dict[str, Any]:
    conn = await get_connection()
    try:
        session_count = await conn.fetchval(
            "SELECT COUNT(*) FROM chat_sessions WHERE user_id = $1",
            user_id,
        )
        message_count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM messages m
            JOIN chat_sessions s ON s.id = m.session_id
            WHERE s.user_id = $1
            """,
            user_id,
        )
        runs = await conn.fetch(
            """
            SELECT r.query, r.status, r.intent, r.confidence_score, r.duration_ms, r.created_at
            FROM research_runs r
            JOIN chat_sessions s ON s.id = r.session_id
            WHERE s.user_id = $1
            ORDER BY r.created_at DESC
            LIMIT 50
            """,
            user_id,
        )
        avg_conf = await conn.fetchval(
            """
            SELECT AVG(r.confidence_score) FROM research_runs r
            JOIN chat_sessions s ON s.id = r.session_id
            WHERE s.user_id = $1 AND r.confidence_score IS NOT NULL
            """,
            user_id,
        )
        return {
            "session_count": session_count or 0,
            "message_count": message_count or 0,
            "avg_confidence": float(avg_conf) if avg_conf else None,
            "recent_runs": [row_to_dict(r) for r in runs],
        }
    finally:
        await conn.close()
