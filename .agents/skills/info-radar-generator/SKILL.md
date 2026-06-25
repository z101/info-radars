# Info Radar Generator

Generates self-contained radar skills for scraping and analyzing blog/feed websites.

## Purpose

Given a site URL and description, this skill creates a new `.agents/skills/<site>-radar/` folder with:

- `SKILL.md` — instructions for scraping + analysis tailored to the site
- `scraper/` — full scraper package with custom parser for the target site
- `tests/` — test suite with HTML fixtures
- `data/` — runtime directories

Query files live in the workspace root under `queries/<site>-radar/` — they are use-case definitions that the user edits frequently and are shared across all skills.
Generated reports land in the workspace root under `reports/<site>-radar/` — they are auto-generated artifacts not tracked in git.

## Template Source

The template is based on `../hackaday-blog-radar/` — a working self-contained radar skill for Hackaday.

## To Generate a New Radar

1. Describe the target site (URL, article list structure, content structure)
2. This skill will create `../<site>-radar/` with adapted code
3. Customize the parser selectors for the target site's HTML
4. Run `pytest tests/ -v` to verify parsing
5. Run a dry scrape to validate end-to-end

## Future

As more radars are created, common patterns will be extracted into shared templates.