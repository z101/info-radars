# info-radar

Semantic analysis of blog articles. Each site has a self-contained radar skill under `.agents/skills/<site>-radar/`.

All radars follow the same contract: `SKILL.md` with scrape + analyze instructions, scraper package, pytest suite, and a `data/` directory for SQLite storage.

## Workflow

1. User specifies a target site (or "all"). Find the matching skill directory under `.agents/skills/<site>-radar/`.
2. Load that skill's `SKILL.md` — it contains site-specific scrape + analyze instructions.
3. Scraper saves articles to `data/<site>.db` inside the skill.
4. Read the user's query. Resolution order:
   - `queries/<query>.md` (shared, any radar)
   - `queries/<site>-radar/<query>.md` (skill-specific)
   If no file exists, ask the user to describe what they're looking for and create one.
5. AI processes all articles via parallel subagents, scoring against the query.
6. Writes report to `reports/<site>-radar/<query>_YYYY-MM-DD.md`.

## Available Skills

All skills live under `.agents/skills/<name>/`. Each has a `SKILL.md` with full instructions.

| Skill | Directory | Auto-detection Triggers |
|-------|-----------|------------------------|
| **hackaday-blog-radar** | `.agents/skills/hackaday-blog-radar/` | User mentions hackaday.com, LED Hacks, 3D Printing Hacks, or wants to scrape articles |
| **radio-ru-radar** | `.agents/skills/radio-ru-radar/` | User mentions radio.ru, журнал Радио, архив радиожурнала, "Содержание номера", или wants to scrape articles from radio.ru archive |
| **sqlite-query** | `.agents/skills/sqlite-query/` | User mentions `.db`/`.sqlite` path, "база данных", "бд", "sqlite", "кеш", "сколько записей", "покажи данные из базы", "выполни запрос", or asks about counts/stats/aggregations from a database |

### Auto-detection Priority

When the user asks about **data in a database** (counts, search, stats, SQL queries, `.db` file paths):

1. **First** try to load `sqlite-query` — it handles ad-hoc DB queries
2. **Only if** the question requires scraping new content (not querying existing data), use a domain radar skill instead

Domain skills (`*-radar/`) are for scraping & analyzing articles. `sqlite-query` is for ad-hoc database queries against already-scraped SQLite databases.

## Notes

- Venv is in repo root: `.venv\Scripts\activate` (from repo root).
  From a skill directory (`.agents/skills/<site>-radar/`), use `..\..\..\.venv\Scripts\python <flags>`.
- Each skill is self-contained — run commands from within the skill directory
- After loading any skill via the `skill` tool, always read `<skill_dir>/SKILL.md` from disk — the inline tool output may be truncated or outdated.