# info-radar

Semantic analysis of blog articles. Each site has a self-contained radar skill under `.agents/skills/`.

## Workflow

1. Load skill `.agents/skills/hackaday-blog-radar/SKILL.md` to scrape + analyze Hackaday LED Hacks
2. Scraper saves to SQLite (`data/hackaday.db` inside the skill)
3. AI processes all articles via parallel subagents
4. Writes `../../../reports/hackaday-blog-radar/led-hacks-report_YYYY-MM-DD.md`

## Adding a new site

Use the `.agents/skills/info-radar-generator/` skill to scaffold a new radar.

## Notes

- Use venv: `.venv\Scripts\activate`
- Each skill is self-contained — run commands from within the skill directory