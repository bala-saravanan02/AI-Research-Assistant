from typing import Any
from urllib.parse import urlparse


def _unique_urls(researched_results: list[dict[str, Any]]) -> list[str]:
    urls: list[str] = []
    for entry in researched_results:
        if not isinstance(entry, dict) or entry.get("status") != "success":
            continue
        for item in entry.get("sources") or []:
            if isinstance(item, dict):
                url = (item.get("url") or "").strip()
            else:
                url = str(item).strip()
            if url.startswith("http") and url not in urls:
                urls.append(url)
    return urls


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def compute_research_confidence(
    researched_results: list[dict[str, Any]],
    llm_score: float | None = None,
) -> tuple[float, dict[str, Any]]:
    # Model self-assessment is useful only as a small calibration signal.  Missing
    # metadata must not silently turn into a plausible-looking fixed score.
    llm_part = max(0.0, min(1.0, float(llm_score))) if llm_score is not None else 0.0

    if not researched_results:
        breakdown = {
            "sub_question_success_rate": 0.0,
            "source_coverage": 0.0,
            "domain_diversity": 0.0,
            "evidence_density": 0.0,
            "llm_calibration": round(llm_part, 3),
        }
        return 0.0, breakdown

    total = len(researched_results)
    successes = sum(1 for r in researched_results if r.get("status") == "success")
    blocked = sum(
        1
        for r in researched_results
        if r.get("status") in {"blocked", "failed"}
    )
    non_empty = sum(
        1
        for r in researched_results
        if r.get("status") == "success" and len(str(r.get("data") or "")) > 80
    )
    urls = _unique_urls(researched_results)
    domains = {d for u in urls if (d := _domain(u))}

    success_rate = successes / total
    evidence_density = non_empty / total
    source_coverage = min(1.0, len(urls) / 6.0)
    domain_diversity = min(1.0, len(domains) / 4.0) if domains else 0.0
    blocked_penalty = min(0.35, 0.12 * blocked)

    score = (
        0.28 * success_rate
        + 0.32 * source_coverage
        + 0.15 * domain_diversity
        + 0.15 * evidence_density
        + 0.10 * llm_part
        - blocked_penalty
    )
    if not urls:
        score = min(score, 0.32)
    score = round(max(0.0, min(1.0, score)), 3)

    breakdown = {
        "sub_question_success_rate": round(success_rate, 3),
        "source_coverage": round(source_coverage, 3),
        "domain_diversity": round(domain_diversity, 3),
        "evidence_density": round(evidence_density, 3),
        "llm_calibration": round(llm_part, 3),
    }
    return score, breakdown
