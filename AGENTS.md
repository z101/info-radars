# info-radar

Semantic analysis of blog articles. Each site has a self-contained radar skill under `.agents/skills/<site>-radar/`.

All radars follow the same contract: `SKILL.md` with scrape + analyze instructions, scraper package, pytest suite, and a `data/` directory for SQLite storage.

## Workflow

1. User specifies a target site (or "all"). Find the matching skill directory under `.agents/skills/<site>-radar/`.
2. Load that skill's `SKILL.md` — it contains site-specific scrape + analyze instructions.
3. Scraper saves articles to `data/<site>.db` inside the skill.
4. Read the user's query from `queries/<site>-radar/<query>.md`. If none exists, ask the user to describe what they're looking for and create one.
5. AI processes all articles via parallel subagents, scoring against the query.
6. Writes report to `reports/<site>-radar/<query>_YYYY-MM-DD.md`.

## Available Radars

Discoverable by listing `.agents/skills/` for directories matching `*-radar/`.

## Notes

- Use venv: `.venv\Scripts\activate`
- Each skill is self-contained — run commands from within the skill directory
- For SQLite queries (count, search, stats) — load `sqlite-query` skill, NOT the domain skill. Domain skills are for scraping/analyzing, not ad-hoc DB queries.
- After loading any skill via the `skill` tool, always read `<skill_dir>/SKILL.md` from disk — the inline tool output may be truncated or outdated.