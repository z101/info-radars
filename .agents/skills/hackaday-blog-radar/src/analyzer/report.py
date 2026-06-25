import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from analyzer.config import DEFAULT_ANALYZE_CONFIG
from database import Database


def generate_report(
    db: Database,
    category: str,
    query_name: str,
    query_hash: str,
    rubric_hash: str,
    min_total: int = 0,
    top: int | None = None,
) -> str | None:
    """Generate a CSV report. Returns the path to the file, or None if no data."""
    report = db.get_analysis_report(
        category, query_hash, rubric_hash,
        min_total=min_total, top=top,
    )
    if not report:
        return None

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    reports_dir = Path("../../../reports/hackaday-blog-radar")
    reports_dir.mkdir(parents=True, exist_ok=True)
    csv_path = reports_dir / f"{category}_analysis_{query_name}_{today}.csv"

    criteria_keys = list(DEFAULT_ANALYZE_CONFIG.get("criteria", {}).keys())
    fieldnames = ["id", "title", "date", "url", "author", "tags"] + criteria_keys + ["total", "comment", "filter_reason"]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in report:
            row = {
                "id": r["id"],
                "title": r["title"],
                "date": r["date"],
                "url": r["url"],
                "author": r["author"] or "",
                "tags": ", ".join(r["tags"]) if r["tags"] else "",
                "total": r["total"],
                "comment": r["comment"] or "",
                "filter_reason": r["filter_reason"] or "",
            }
            for k in criteria_keys:
                row[k] = r["scores"].get(k, 0)
            writer.writerow(row)

    print(f"\nAnalysis report: {len(report)} article(s) scored")
    print(f"Query: {query_name}")
    print(f"Saved: {csv_path}")
    print()

    top_n = min(10, len(report))
    print(f"Top {top_n}:")
    print("-" * 70)
    for r in report[:top_n]:
        print(f"[{r['id']:4d}] {r['total']:3d}pt  {r['title'][:55]}")
        print(f"       {r['date']}  {r['url']}")
        if r["comment"]:
            print(f"       {r['comment'][:100]}")
        print()

    return str(csv_path)