import argparse
import json
import os
import sys


def load_query_text(query_path: str) -> str:
    with open(query_path, "r", encoding="utf-8-sig") as f:
        return f.read().strip()


def load_candidates(candidates_path: str) -> list[dict]:
    with open(candidates_path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("candidates JSON must be an array")
    return data


def format_article(i: int, a: dict) -> str:
    ym = f"{a['year']:04d}-{a['month']:02d}"
    topic = a.get("topic", "")
    author = (a.get("author") or "").strip()
    section = (a.get("section") or "").strip()
    excerpt = (a.get("excerpt") or "").strip()

    parts = f'[{ym}] "{topic}"'
    if author:
        parts += f" by {author}"
    if section:
        parts += f" [{section}]"
    if excerpt:
        if len(excerpt) > 200:
            excerpt = excerpt[:197] + "..."
        parts += f" — {excerpt}"
    return f"{i}. {parts}"


def estimate_tokens(text: str) -> int:
    return len(text) // 4


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
        "- Base your score primarily on the excerpt and title. If the excerpt is empty, use the title and section only.\n"
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
        "You are an expert in electronics, radio engineering, and DIY.\n"
        "Rate how relevant each article is to the user's query.\n\n"
        f"User query:\n{query_text}\n\n"
        "For each article you have: title, author, section, year, month, and a short excerpt.\n"
        f"{rubric}\n"
        f"{rules}\n\n"
        f"{output_fmt}\n\n"
        "Articles:\n"
        f"{articles_text}"
    )
    return prompt


def main():
    parser = argparse.ArgumentParser(
        description="Format candidates JSON into a search prompt"
    )
    parser.add_argument(
        "--candidates", required=True, help="Path to candidates JSON file"
    )
    parser.add_argument(
        "--query", required=True, help="Path to query file"
    )
    parser.add_argument(
        "--output", required=True, help="Path to output prompt file"
    )
    args = parser.parse_args()

    query_text = load_query_text(args.query)
    candidates = load_candidates(args.candidates)

    prompt = build_prompt(query_text, candidates)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(prompt)

    tokens_est = estimate_tokens(prompt)
    print(f"Articles: {len(candidates)}")
    print(f"Prompt size: {len(prompt)} chars, ~{tokens_est} tokens")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()