DEFAULT_ANALYZE_CONFIG: dict = {
    "max_score": 100,
    "batch_size": 100,
    "parallel_agents": 10,
    "prompt_search": (
        "You are an expert in electronics, embedded systems, and DIY hardware.\n"
        "Rate how relevant each article is to the user's query.\n\n"
        "User query:\n{user_query}\n\n"
        "For each article you have: title, author, tags, date, and a short excerpt.\n"
        "Score relevance on a 0-100 scale using this rubric:\n\n"
        "  Score  | Meaning\n"
        "  -------|--------\n"
        "  81-100 | Core topic match. Article is directly about the query subject.\n"
        "  61-80  | Clearly relevant. Shares the same domain/technology as the query.\n"
        "  41-60  | Somewhat relevant. Mentions related concepts but isn't focused on the query.\n"
        "  21-40  | Tangential. The topic touches the query only peripherally.\n"
        "   0-20  | Unrelated or off-topic.\n\n"
        "Rules:\n"
        "- Base your score primarily on the excerpt and title. If the excerpt is empty, use the title and tags only.\n"
        "- Score strictly — use the whole 0-100 range.\n"
        "- When in doubt, prefer the lower end of the range.\n"
        "- Write the reason in the same language as the user query.\n\n"
        "Return a strict JSON array, no markdown, no explanation:\n"
        '[{"id": N, "relevance": 0, "reason": "..."}, ...]\n\n'
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