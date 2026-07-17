def format_article(i: int, a: dict) -> str:
    date = a.get("date", "")
    title = a.get("title", "")
    author = (a.get("author") or "").strip()
    tags = ", ".join(a.get("tags", [])) if a.get("tags") else ""
    excerpt = (a.get("excerpt") or "").strip()

    parts = f'[{date}] "{title}"'
    if author:
        parts += f" by {author}"
    if tags:
        parts += f" [{tags}]"
    if excerpt:
        if len(excerpt) > 200:
            excerpt = excerpt[:197] + "..."
        parts += f" — {excerpt}"
    return f"{i}. {parts}"


def build_prompt(query_text: str, articles: list[dict]) -> str:
    rubric = (
        "Score relevance on a 0-100 scale using this rubric:\n\n"
        "  Score  | Meaning\n"
        "  -------|--------\n"
        "  81-100 | Core topic match. Article is directly about the query subject.\n"
        "  61-80  | Clearly relevant. Shares the same domain/technology as the query.\n"
        "  41-60  | Somewhat relevant. Mentions related concepts but isn't focused on the query.\n"
        "  21-40  | Tangential. The topic touches the query only peripherally.\n"
        "   0-20  | Unrelated or off-topic.\n"
    )

    rules = (
        "Rules:\n"
        "- Base your score primarily on the excerpt and title. If the excerpt is empty, use the title and tags only.\n"
        "- Score strictly - use the whole 0-100 range.\n"
        "- When in doubt, prefer the lower end of the range.\n"
        "- Write the reason in the same language as the user query.\n"
    )

    output_fmt = (
        'Return a strict JSON array, no markdown, no explanation:\n'
        '[{"id": N, "relevance": 0, "reason": "..."}, ...]'
    )

    articles_lines = [format_article(i + 1, a) for i, a in enumerate(articles)]
    articles_text = "\n".join(articles_lines)

    prompt = (
        "You are an expert in electronics, embedded systems, and DIY hardware.\n"
        "Rate how relevant each article is to the user's query.\n\n"
        f"User query:\n{query_text}\n\n"
        "For each article you have: title, author, tags, date, and a short excerpt.\n"
        f"{rubric}\n"
        f"{rules}\n\n"
        f"{output_fmt}\n\n"
        "Articles:\n"
        f"{articles_text}"
    )
    return prompt


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


def format_interest_articles(articles: list[dict]) -> str:
    lines = []
    for a in articles:
        tags = ", ".join(a.get("tags", [])) if a.get("tags") else "\u2014"
        lines.append(f"[{a['id']}] {a['title']} ({a['date']})")
        lines.append(f"   Score: {a['total']}/100  URL: {a['url']}")
        lines.append(f"   Tags: {tags}")
        if a.get("comment"):
            lines.append(f"   Why: {a['comment']}")
        lines.append("")
    return "\n".join(lines)