import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

_src = Path(__file__).parent.parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from database import Database


def _short_date(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso


def export_json(
    db: Database,
    category: str,
    output_dir: str = "data",
    since: Optional[str] = None,
) -> str:
    articles = db.export_articles(category, since)
    output_path = Path(output_dir) / f"{category}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    return str(output_path)


def format_info(db: Database, category: Optional[str] = None) -> str:
    lines = []
    if category:
        info = db.get_category_info(category)
        session = db.get_session_info(category)
        if not info or info["total_articles"] == 0:
            return f"No data for category '{category}'."

        lines.append(
            f"{category}: {info['total_articles']} articles "
            f"({info['full_text_count']} full text)"
        )
        if session:
            scraped = _short_date(session["started_at"])
            lines.append(f"  Last scrape: {scraped} (session #{session['id']}, {session['status']})")
        if info["earliest"]:
            lines.append(f"  Date range:  {info['earliest']} .. {info['latest']}")
    else:
        categories = db.get_categories()
        if not categories:
            return "No data in database."
        lines.append("Categories in database:")
        for c in categories:
            lines.append(f"  {c['name']:30s} {c['count']} articles")
    return "\n".join(lines)