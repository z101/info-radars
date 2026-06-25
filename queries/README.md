# Query files

Each file describes a relevance goal in free text. The agent reads the file and uses its content as `user_query` when running the analysis pipeline.

Subdirectories are named after the skill: `queries/<skill-name>/<query-name>.md`.

## Usage

```
find @../../../queries/hackaday-blog-radar/led_sculptures.md
```

The agent will:
1. Read the query file
2. Run the filter → rerank pipeline against the scraped article corpus
3. Save scores to the skill's database (keyed by query + rubric + content hashes)
4. Output a ranked CSV report to `../../../reports/hackaday-blog-radar/`

## Cache behaviour

- Scores are cached by `(query_hash, rubric_hash, content_hash)`.
- Changing this file → new `query_hash` → fresh analysis run; old scores are preserved as history.
- Changing `analyze_config.yaml` criteria/weights → new `rubric_hash` → same effect.
- Re-scraping an article with updated content → new `content_hash` → that article is re-scored.

## Adding a new query

Create a new `.md` file in the skill's subdirectory with a plain-text description of what you are looking for.
The filename (without extension) becomes the `query_name` used in report filenames.