DEFAULT_ANALYZE_CONFIG: dict = {
    "max_score": 100,
    "batch_size": 50,
    "parallel_agents": 5,
    "prompt_scorer": (
        "You are an expert in electronics, radio engineering, and DIY.\n"
        "Rate how relevant each article is to the user's query.\n\n"
        "User query:\n{user_query}\n\n"
        "For each article you have: title, author, section, year, month, and a short excerpt.\n"
        "Score relevance on a 0-100 scale using this rubric:\n\n"
        "  Score  | Meaning\n"
        "  -------|--------\n"
        "  81-100 | Core topic match. Article is directly about the query subject.\n"
        "  61-80  | Clearly relevant. Shares the same domain/technology as the query.\n"
        "  41-60  | Somewhat relevant. Mentions related concepts but isn't focused on the query.\n"
        "  21-40  | Tangential. The topic touches the query only peripherally.\n"
        "   0-20  | Unrelated or off-topic.\n\n"
        "Rules:\n"
        "- Base your score primarily on the excerpt and title. If the excerpt is empty, use the title and section only.\n"
        "- Score strictly — use the whole 0-100 range.\n"
        "- When in doubt, prefer the lower end of the range.\n"
        "- Write the reason in the same language as the user query.\n\n"
        "Return a strict JSON array, no markdown, no explanation:\n"
        '[{"id": N, "relevance": 0, "reason": "..."}, ...]\n\n'
        "Articles:\n{articles}"
    ),
    "prompt_interesting_to_query": (
        "Ты — аналитик, который по набору статей из журнала «Радио», "
        "отмеченных пользователем как интересные, "
        "составляет поисковый запрос для поиска похожих статей.\n\n"
        "Ниже — список статей, которые пользователь посчитал интересными. "
        "Проанализируй их общие темы, технологии, разделы и сформулируй "
        "поисковый запрос на русском языке (2-3 предложения), который отражает "
        "суть интереса пользователя.\n\n"
        "Статьи:\n{articles}\n\n"
        "Верни ТОЛЬКО текст запроса, без пояснений и форматирования."
    ),
}
