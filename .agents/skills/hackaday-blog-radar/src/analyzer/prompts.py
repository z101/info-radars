def build_criteria_block(criteria: dict) -> str:
    lines = []
    for key, cfg in criteria.items():
        weight = cfg.get("weight", 0)
        desc = cfg.get("desc", "")
        lines.append(f"  {key} (0-{weight}): {desc}")
    return "\n".join(lines)


def format_filter_articles(articles: list[dict]) -> str:
    lines = []
    for a in articles:
        tags = ", ".join(a.get("tags", [])) if a.get("tags") else "\u2014"
        lines.append(f"[ID {a['id']}] {a['title']}")
        lines.append(f"Date: {a.get('date', '')}  Tags: {tags}")
        excerpt = (a.get("excerpt") or "")[:300]
        if excerpt:
            lines.append(f"Excerpt: {excerpt}")
        lines.append("")
    return "\n".join(lines)


def format_rerank_articles(articles: list[dict]) -> str:
    lines = []
    for a in articles:
        tags = ", ".join(a.get("tags", [])) if a.get("tags") else "\u2014"
        lines.append(f"[ID {a['id']}] {a['title']}")
        lines.append(f"Date: {a.get('date', '')}  Tags: {tags}")
        if a.get("author"):
            lines.append(f"Author: {a['author']}")
        content = (a.get("content_md") or a.get("excerpt") or "")
        if content:
            lines.append(f"Content:\n{content}")
        comments = a.get("comments", [])
        if comments:
            lines.append("Comments:")
            for c in comments:
                author = c.get("author", "Anonymous")
                lines.append(f"  [{author}] {c.get('content_md', '')}")
        lines.append("")
    return "\n".join(lines)