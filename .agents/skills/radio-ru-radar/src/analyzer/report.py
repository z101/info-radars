import json
from datetime import datetime, timezone
from pathlib import Path

from analyzer.config import DEFAULT_ANALYZE_CONFIG
from analyzer.normalizer import normalize_scores
from scraper.parser import make_month_url
from xlsx_exporter import export_to_xlsx, SEARCH_COLUMNS, SEARCH_HEADER_NAMES, SEARCH_EDITABLE


def generate_report(
    db,
    query_name: str,
    query_hash: str,
    rubric_hash: str,
    min_total: int = 0,
    top: int | None = None,
) -> str | None:
    """Generate an XLSX search report with normalized scores."""
    report = db.get_search_report(
        query_hash, rubric_hash,
        min_total=min_total, top=top,
    )
    if not report:
        return None

    normalize_scores(report, key="total")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    reports_dir = Path("../../../reports/radio-ru-radar")
    reports_dir.mkdir(parents=True, exist_ok=True)
    xlsx_path = reports_dir / f"search_{query_name}_{today}.xlsx"

    rows = []
    for r in report:
        row = {
            "id": r["id"],
            "score": r["total"],
            "normalized": r.get("total_normalized", 0),
            "is_interesting": r["is_interesting"],
            "is_read": r["is_read"],
            "date": f"{r['year']:04d}-{r['month']:02d}",
            "month_url": make_month_url(r["year"], r["month"]),
            "url": r["detail_url"] or "",
            "pdf_url": r.get("pdf_url") or "",
            "page": r["page"] or "",
            "section": r["section"] or "",
            "author": r["author"] or "",
            "excerpt": r["excerpt"] or "",
            "topic": r["topic"],
        }
        rows.append(row)

    export_to_xlsx(
        rows, str(xlsx_path),
        columns=SEARCH_COLUMNS,
        header_names=SEARCH_HEADER_NAMES,
        editable=SEARCH_EDITABLE,
    )

    print(f"\nAnalysis report: {len(report)} article(s) scored")
    print(f"Query: {query_name}")
    print(f"Saved: {xlsx_path}")
    print()

    top_n = min(10, len(report))
    print(f"Top {top_n} (normalized scores):")
    print("-" * 70)
    for r in report[:top_n]:
        ym = f"{r['year']:04d}-{r['month']:02d}"
        score = f"{r.get('total_normalized', r['total']):.0f}" if isinstance(r.get('total_normalized'), (int, float)) else str(r['total'])
        print(f"  [{r['id']:4d}] {score:>3s}pt  {r['topic'][:55]}")
        print(f"         {ym}  [{r['section']}] {r['detail_url']}")
        if r["comment"]:
            print(f"         {r['comment'][:100]}")
        print()

    return str(xlsx_path)


def generate_report_text(
    db,
    query_name: str,
    query_hash: str,
    rubric_hash: str,
    min_total: int = 0,
    top: int | None = None,
) -> str | None:
    report = db.get_search_report(
        query_hash, rubric_hash,
        min_total=min_total, top=top,
    )
    if not report:
        return None

    normalize_scores(report, key="total")

    lines = []
    lines.append(f"Results for '{query_name}':\n")
    for r in report[:top or 20]:
        ym = f"{r['year']:04d}-{r['month']:02d}"
        score = f"{r.get('total_normalized', r['total']):.0f}" if isinstance(r.get('total_normalized'), (int, float)) else str(r['total'])
        lines.append(f"  [{r['id']:4d}] ({score:>3s}pt) {r['topic']}")
        lines.append(f"         {ym}  [{r['section']}]")
        if r["comment"]:
            lines.append(f"         {r['comment'][:200]}")
        lines.append("")
    return "\n".join(lines)