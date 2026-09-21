import json
import os
import logging
import re
from typing import Any

import asyncpg
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

logger = logging.getLogger(__name__)

CACHE_MAX_DISTANCE = float(os.getenv("CACHE_MAX_DISTANCE", "0.10"))
CACHE_TTL_DAYS = int(os.getenv("CACHE_TTL_DAYS", "7"))
CACHE_TOKEN_OVERLAP = float(os.getenv("CACHE_TOKEN_OVERLAP", "0.42"))
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1536"))


def _token_overlap(a: str, b: str) -> float:
    wa = set(re.findall(r"[a-z0-9]{3,}", (a or "").lower()))
    wb = set(re.findall(r"[a-z0-9]{3,}", (b or "").lower()))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


async def ensure_cache_schema(conn: asyncpg.Connection) -> None:
    await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    await conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS semantic_cache_table (
            id SERIAL PRIMARY KEY,
            historical_query TEXT,
            query_embedding vector({EMBEDDING_DIM}),
            cached_report TEXT,
            confidence_score DOUBLE PRECISION,
            source_count INTEGER,
            sources JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
    )
    await conn.execute(
        "ALTER TABLE semantic_cache_table ADD COLUMN IF NOT EXISTS confidence_score DOUBLE PRECISION;"
    )
    await conn.execute(
        "ALTER TABLE semantic_cache_table ADD COLUMN IF NOT EXISTS source_count INTEGER;"
    )
    await conn.execute(
        "ALTER TABLE semantic_cache_table ADD COLUMN IF NOT EXISTS sources JSONB;"
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS semantic_cache_query_idx
        ON semantic_cache_table (historical_query);
        """
    )
    try:
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS semantic_cache_embedding_hnsw
            ON semantic_cache_table
            USING hnsw (query_embedding vector_cosine_ops);
            """
        )
    except Exception as e:
        logger.info("HNSW cache index not created (pgvector may lack HNSW): %s", e)


def _embed_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=os.getenv("open_router_url"),
        api_key=os.getenv("open_router_api_key"),
    )


async def _embed_query(text: str) -> str:
    embedding_response = await _embed_client().embeddings.create(
        model=os.getenv("embedding_model"),
        input=text,
    )
    query_vector = embedding_response.data[0].embedding
    if len(query_vector) != EMBEDDING_DIM:
        raise ValueError(
            f"Embedding dim {len(query_vector)} != expected {EMBEDDING_DIM}"
        )
    return f"[{','.join(map(str, query_vector))}]"


def _row_get(row: asyncpg.Record, key: str, default: Any = None) -> Any:
    try:
        value = row[key]
    except (KeyError, Exception):
        return default
    return default if value is None else value


def _hit_payload(row: asyncpg.Record, *, exact: bool) -> dict[str, Any]:
    cached = _row_get(row, "cached_report", "") or ""
    answer = cached.split("```json", 1)[0].strip() or cached
    score = _row_get(row, "confidence_score", None)
    sources = _row_get(row, "sources", []) or []
    if isinstance(sources, str):
        try:
            sources = json.loads(sources)
        except json.JSONDecodeError:
            sources = []
    distance_raw = _row_get(row, "distance", 0.0)
    distance = float(distance_raw) if distance_raw is not None else 0.0
    listed = len(sources) if isinstance(sources, list) else 0
    source_count = int(_row_get(row, "source_count", listed) or listed)
    logger.info(
        "Semantic cache hit (%s, distance=%.3f, sources=%s, confidence=%.3f)",
        "exact" if exact else "vector",
        distance,
        source_count,
        float(score or 0.0),
    )
    return {
        "cache_hit": True,
        "final_summary": cached,
        "confidence_score": float(score) if score is not None else None,
        "confidence_breakdown": {
            "source_coverage": min(1.0, source_count / 6) if source_count else 0.0,
            "cached_source_count_ratio": min(1.0, source_count / 6) if source_count else 0.0,
            "llm_calibration": float(score) if score is not None else 0.0,
        },
        "last_report": {
            "query": _row_get(row, "historical_query"),
            "answer": answer,
            "sub_questions": [],
            "sources": sources if isinstance(sources, list) else [],
            "confidence": float(score) if score is not None else None,
        },
        "messages": [{"role": "assistant", "content": answer}],
        "_cache_meta": {
            "exact": exact,
            "distance": distance,
            "source_count": source_count,
        },
    }


async def lookup_semantic_cache(query: str) -> dict[str, Any]:
    db_url = os.getenv("DATABASE_URL")
    normalized = (query or "").lower().strip()
    if not db_url or len(normalized) < 8:
        return {"cache_hit": False}

    conn = None
    try:
        conn = await asyncpg.connect(db_url)
        await ensure_cache_schema(conn)

        exact = await conn.fetchrow(
            """
            SELECT historical_query, cached_report, confidence_score, source_count, sources,
                   0::float8 AS distance
            FROM semantic_cache_table
            WHERE historical_query = $1
              AND created_at > NOW() - make_interval(days => $2::int)
            ORDER BY created_at DESC
            LIMIT 1;
            """,
            normalized,
            CACHE_TTL_DAYS,
        )
        if exact:
            if not _row_get(exact, "sources", []):
                logger.info("Exact cache entry rejected: no stored sources")
                return {"cache_hit": False}
            return _hit_payload(exact, exact=True)

        vector_str = await _embed_query(normalized)
        row = await conn.fetchrow(
            """
            SELECT historical_query, cached_report, confidence_score, source_count, sources,
                   (query_embedding <=> $1::vector) AS distance
            FROM semantic_cache_table
            WHERE created_at > NOW() - make_interval(days => $2::int)
            ORDER BY query_embedding <=> $1::vector
            LIMIT 1;
            """,
            vector_str,
            CACHE_TTL_DAYS,
        )
        if row and row["distance"] is not None and row["distance"] < CACHE_MAX_DISTANCE:
            cached_q = _row_get(row, "historical_query", "") or ""
            overlap = _token_overlap(normalized, cached_q)
            if overlap < CACHE_TOKEN_OVERLAP:
                logger.info(
                    "Vector cache rejected (distance=%.3f overlap=%.2f < %.2f vs '%s')",
                    row["distance"],
                    overlap,
                    CACHE_TOKEN_OVERLAP,
                    cached_q[:80],
                )
                return {"cache_hit": False}
            # A semantic hit is reusable only when it has attributable evidence.
            if not _row_get(row, "sources", []):
                logger.info("Vector cache rejected: entry has no stored sources")
                return {"cache_hit": False}
            return _hit_payload(row, exact=False)

        nearest = f"{row['distance']:.3f}" if row and row["distance"] is not None else "n/a"
        logger.info("Vector cache miss (nearest distance=%s, threshold=%.3f)", nearest, CACHE_MAX_DISTANCE)
        return {"cache_hit": False}
    except Exception as e:
        logger.warning("Semantic cache lookup failed: %s", e)
        return {"cache_hit": False}
    finally:
        if conn is not None:
            await conn.close()


async def persist_semantic_cache(
    query: str,
    report: str,
    *,
    confidence_score: float | None = None,
    sources: list | None = None,
) -> None:
    db_url = os.getenv("DATABASE_URL")
    normalized = (query or "").lower().strip()
    if not db_url or len(normalized) < 8 or not (report or "").strip():
        return
    if "Fallback static context" in report:
        return

    source_list = sources or []
    source_count = len(source_list)
    conn = None
    try:
        vector_str = await _embed_query(normalized)
        conn = await asyncpg.connect(db_url)
        await ensure_cache_schema(conn)
        await conn.execute(
            "DELETE FROM semantic_cache_table "
            "WHERE created_at < NOW() - make_interval(days => $1::int);",
            CACHE_TTL_DAYS,
        )

        existing = await conn.fetchrow(
            """
            SELECT id
            FROM semantic_cache_table
            WHERE historical_query = $1
            LIMIT 1;
            """,
            normalized,
        )
        if existing:
            await conn.execute(
                """
                UPDATE semantic_cache_table
                SET cached_report = $2,
                    confidence_score = $3,
                    source_count = $4,
                    sources = $5::jsonb,
                    created_at = NOW()
                WHERE id = $1;
                """,
                existing["id"],
                report,
                confidence_score,
                source_count,
                json.dumps(source_list),
            )
            logger.info("Semantic cache updated exact-query entry.")
            return

        await conn.execute(
            """
            INSERT INTO semantic_cache_table (
                historical_query, query_embedding, cached_report,
                confidence_score, source_count, sources
            )
            VALUES ($1, $2, $3, $4, $5, $6::jsonb);
            """,
            normalized,
            vector_str,
            report,
            confidence_score,
            source_count,
            json.dumps(source_list),
        )
        logger.info("Semantic cache write-back completed (sources=%s).", source_count)
    except Exception as e:
        logger.warning("Semantic cache write-back failed: %s", e)
    finally:
        if conn is not None:
            await conn.close()
