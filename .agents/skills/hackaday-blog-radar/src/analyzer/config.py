DEFAULT_ANALYZE_CONFIG: dict = {
    "criteria": {
        "topical_relevance": {"weight": 35, "desc": "How well the article matches the user's query topic"},
        "technical_depth": {"weight": 25, "desc": "Depth: schematics, code, components, measurements"},
        "practical_applicability": {"weight": 20, "desc": "Reproducibility / usability for the user's own project"},
        "novelty": {"weight": 10, "desc": "Originality of the approach relative to typical projects"},
        "comment_signal": {"weight": 10, "desc": "Technically valuable comments"},
    },
    "batch_size": 20,
    "parallel_agents": 5,
    "primary_filter": {
        "enabled": True,
        "batch_size": 100,
    },
    "prompt_filter": (
        "You are a relevance triage assistant. Your job is to quickly decide whether each article "
        "is potentially relevant to the user's query, based ONLY on title, excerpt and tags.\n\n"
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
        "You are an expert in electronics and embedded systems.\n\n"
        "User's relevance query:\n{user_query}\n\n"
        "Score each article on 5 criteria. Weights indicate the maximum score per criterion:\n\n"
        "{criteria_block}\n\n"
        "total = sum of all criterion scores.\n\n"
        "Comment scoring (noise is filtered implicitly, not as a separate step):\n"
        "- Signal (count): specific components, alternative circuits, corrections, references\n"
        "- Noise (ignore, no score weight): 'cool!', '+1', off-topic, empty chatter\n"
        "- No comments → comment_signal = 0, other criteria unchanged\n\n"
        "Return a strict JSON array, no markdown, no explanation:\n"
        '[{"id": N, "scores": {"topical_relevance": 0, ...}, "total": 0, "comment": "..."}, ...]\n\n'
        "Articles:\n{articles}"
    ),
    "prompt_trend_interpretation": (
        "Ты — аналитик трендов Hackaday. Проанализируй агрегированные данные за период "
        "и напиши краткий анализ на русском (2-4 абзаца).\n\n"
        "{trend_data}\n\n"
        "Опиши:\n"
        "1. Общая активность: сколько статей, комментариев, авторов\n"
        "2. Всплески: статьи с аномально большим числом комментариев — о чём они?\n"
        "3. Частотность ключевых слов: какие темы растут/падают по месяцам\n"
        "4. Новые темы: что появилось в этом периоде и не было раньше\n\n"
        "На русском, фактологично, без воды."
    ),
    "prompt_digest_summary": (
        "Ты готовишь еженедельную сводку для инженера. "
        "Ниже — интерес пользователя и топ статей за период.\n\n"
        "Интерес:\n{interest_text}\n\n"
        "Топ статей:\n{articles}\n\n"
        "Напиши краткую сводку на русском (1-3 абзаца):\n"
        "- Что нового и интересного появилось\n"
        "- Какая статья самая полезная и почему\n"
        "- Есть ли практические проекты, которые можно повторить"
    ),
}