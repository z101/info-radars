import json
import logging
from datetime import datetime, timezone
from typing import Optional

from analyzer.config import DEFAULT_ANALYZE_CONFIG
from analyzer.hashes import compute_params_hash
from database import Database

logger = logging.getLogger(__name__)


def collect_trend_data(
    db: Database,
    category: str,
    period_start: str,
    period_end: str,
    keyword: Optional[str] = None,
) -> dict:
    aggregates = db.get_trend_aggregates(category, period_start, period_end, keyword)

    comment_spikes = db.get_comment_spikes(category, period_start, period_end)

    keywords = [keyword] if keyword else ["hack", "LED", "ESP32", "Arduino", "sensor", "display", "audio"]
    keyword_freq = db.get_keyword_frequency(category, period_start, period_end, keywords)

    lookback_start = f"{int(period_start[:4]) - 1}{period_start[4:]}"
    novel = db.get_novel_topics(category, lookback_start, period_start, period_end)

    return {
        "aggregates": aggregates,
        "comment_spikes": [dict(r) for r in comment_spikes],
        "keyword_frequency": keyword_freq,
        "novel_topics": novel,
    }


def format_trend_data_for_llm(data: dict) -> str:
    lines = []
    a = data["aggregates"]
    lines.append(f"Period: {a['period']['start']} to {a['period']['end']}")
    lines.append(f"Category: {a['category']}")
    lines.append(f"Total articles: {a['total_articles']}")
    lines.append(f"Full texts: {a['full_texts']}")
    lines.append(f"Total comments: {a['total_comments']}")
    if a.get("keyword_matches") is not None:
        lines.append(f"Keyword matches: {a['keyword_matches']}")
    lines.append("")
    if a["top_authors"]:
        lines.append("Top authors:")
        for au in a["top_authors"]:
            lines.append(f"  {au['author']}: {au['count']} articles")
        lines.append("")

    spikes = data["comment_spikes"]
    if spikes:
        lines.append(f"Comment spikes (articles with anomalously high comment count):")
        for s in spikes[:10]:
            lines.append(f"  [{s['id']}] {s['title']} ({s['date']}) — {s['cnt']} comments (avg: {s['avg_cnt']})")
        lines.append("")

    kf = data["keyword_frequency"]
    if kf:
        lines.append("Keyword frequency by month:")
        for kw, months in kf.items():
            if months:
                line = f"  {kw}: " + ", ".join(f"{m['month']}={m['freq']}" for m in months)
                lines.append(line)
        lines.append("")

    novel = data["novel_topics"]
    if novel:
        lines.append(f"Novel topics (articles on topics not seen in the previous year):")
        for n in novel[:10]:
            tags = ", ".join(n["tags"]) if n["tags"] else "-"
            lines.append(f"  [{n['id']}] {n['title']} ({n['date']}) tags: {tags}")
        lines.append("")

    return "\n".join(lines)


def run_trend_analysis(
    db: Database,
    category: str,
    period_start: str,
    period_end: str,
    keyword: Optional[str] = None,
) -> dict:
    params = {"keyword": keyword}
    params_hash = compute_params_hash(params)
    cached = db.get_trend_cache(category, params_hash, period_start, period_end)

    if cached and cached["interpretation_json"]:
        logger.info("Trend analysis cache hit for %s %s-%s", category, period_start, period_end)
        return json.loads(cached["interpretation_json"])

    data = collect_trend_data(db, category, period_start, period_end, keyword)

    sql_data_json = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    params_json = json.dumps(params, ensure_ascii=False)

    db.save_trend_cache(
        category, period_start, period_end,
        params_json, params_hash, sql_data_json,
    )

    return {
        "status": "needs_llm",
        "sql_data": data,
        "formatted": format_trend_data_for_llm(data),
        "params_hash": params_hash,
    }


def save_trend_interpretation(
    db: Database,
    category: str,
    params_hash: str,
    period_start: str,
    period_end: str,
    interpretation: str,
):
    cached = db.get_trend_cache(category, params_hash, period_start, period_end)
    if cached is None:
        logger.warning("No trend cache entry found for save")
        return

    interpretation_json = json.dumps({
        "interpretation": interpretation,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False)

    db.save_trend_cache(
        category, period_start, period_end,
        cached["params_json"], params_hash,
        cached["sql_data_json"], interpretation_json,
    )
