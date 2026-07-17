import json
from datetime import datetime
from pathlib import Path

from analyzer.config import DEFAULT_ANALYZE_CONFIG
from scraper.parser import make_month_url
from xlsx_exporter import export_to_xlsx, SEARCH_COLUMNS, SEARCH_HEADER_NAMES, SEARCH_EDITABLE


def generate_report(
    db,
    query_name: str,
    query_hash: str,
    min_score: int = 0,
    top: int | None = None,
) -> str | None:
    """Generate an XLSX search report with normalized scores."""
    report = db.get_search_report(
        query_hash,
        min_score=min_score, top=top,
    )
    if not report:
        return None

    today = datetime.now().strftime("%Y-%m-%d")
    reports_dir = Path("../../../reports/radio-ru-radar")
    reports_dir.mkdir(parents=True, exist_ok=True)
    xlsx_path = reports_dir / f"search_{query_name}_{today}.xlsx"

    rows = []
    for r in report:
        row = {
            "id": r["id"],
            "score": r["score"],
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
    print(f"Top {top_n} (by date):")
    print("-" * 70)
    for r in report[:top_n]:
        ym = f"{r['year']:04d}-{r['month']:02d}"
        score = f"{r['score']:.0f}"
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
    min_score: int = 0,
    top: int | None = None,
) -> str | None:
    report = db.get_search_report(
        query_hash,
        min_score=min_score, top=top,
    )
    if not report:
        return None

    lines = []
    lines.append(f"Results for '{query_name}':\n")
    for r in report[:top or 20]:
        ym = f"{r['year']:04d}-{r['month']:02d}"
        score = f"{r['score']:.0f}"
        lines.append(f"  [{r['id']:4d}] ({score:>3s}pt) {r['topic']}")
        lines.append(f"         {ym}  [{r['section']}]")
        if r["comment"]:
            lines.append(f"         {r['comment'][:200]}")
        lines.append("")
    return "\n".join(lines)