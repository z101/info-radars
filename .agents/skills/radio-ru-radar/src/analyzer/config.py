DEFAULT_ANALYZE_CONFIG: dict = {
    "criteria": {
        "topical_relevance": {"weight": 35, "desc": "Насколько статья соответствует теме запроса"},
        "technical_depth": {"weight": 25, "desc": "Глубина: схемы, расчёты, компоненты, номиналы"},
        "practical_applicability": {"weight": 20, "desc": "Возможность повторить/использовать в своих проектах"},
        "novelty": {"weight": 10, "desc": "Оригинальность подхода"},
        "historical_value": {"weight": 10, "desc": "Историческая или справочная ценность для радиолюбителя"},
    },
    "batch_size": 20,
    "parallel_agents": 5,
    "primary_filter": {
        "enabled": True,
        "batch_size": 100,
    },
    "prompt_filter": (
        "You are a relevance triage assistant for a Russian radio amateur magazine archive.\n"
        "Your job is to quickly decide whether each article is potentially relevant to the user's query, "
        "based on title, author and section.\n\n"
        "User query:\n{user_query}\n\n"
        "Rules:\n"
        "- When in doubt, KEEP the article (recall-biased).\n"
        "- Drop only articles that are clearly unrelated to the query.\n"
        "- Do not score — just decide keep or drop.\n\n"
        "Return a strict JSON array, no markdown, no explanation:\n"
        '[{"id": N, "keep": true, "reason": "brief reason"}, ...]\n\n'
        "Articles:\n{articles}"
    ),
    "prompt_subagent": (
        "You are an expert in electronics, radio engineering, and DIY.\n\n"
        "User's relevance query:\n{user_query}\n\n"
        "Score each article on 5 criteria. Weights indicate the maximum score per criterion:\n\n"
        "{criteria_block}\n\n"
        "total = sum of all criterion scores.\n\n"
        "Return a strict JSON array, no markdown, no explanation:\n"
        '[{"id": N, "scores": {"topical_relevance": 0, ...}, "total": 0, "comment": "..."}, ...]\n\n'
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