# Query files

Each file describes a relevance goal in free text. The agent reads the file and uses its content as `user_query` when running the analysis pipeline.

Files at the top level (`queries/<query>.md`) are **shared** — usable by any radar skill.
Files in a subdirectory (`queries/<skill>/<query>.md`) are **skill-specific**.

The agent resolves queries in this order:
1. `queries/<query>.md` — shared query
2. `queries/<site>-radar/<query>.md` — skill-specific fallback

## Usage

```
find @../../../queries/led_sculptures.md
```

The agent will:
1. Read the query file
2. Run the filter → rerank pipeline against the scraped article corpus
3. Save scores to the skill's database (keyed by query + rubric + content hashes)
4. Output a ranked report to `../../../reports/<site>-radar/`

## Cache behaviour

- Scores are cached by `(query_hash, rubric_hash, content_hash)`.
- Changing this file → new `query_hash` → fresh analysis run; old scores are preserved as history.
- Changing `analyze_config.yaml` criteria/weights → new `rubric_hash` → same effect.
- Re-scraping an article with updated content → new `content_hash` → that article is re-scored.

## Adding a new query

Create a new `.md` file with a plain-text description of what you are looking for.
Place it at `queries/<query>.md` if it's relevant to multiple radars,
or at `queries/<site>-radar/<query>.md` if it's specific to one skill.
The filename (without extension) becomes the `query_name` used in report filenames.