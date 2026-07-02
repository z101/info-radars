# Hackaday Radar CLI

CLI for scraping and analyzing articles from hackaday.com. Run commands from the skill directory.

## Quick start

```powershell
..\..\..\.venv\Scripts\activate
python src/main.py --category led-hacks --full-text
```

## Flag reference

### Scraping options

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--category <slug>` | `-c` | required | Category slug (e.g. `led-hacks`, `3d-printing-hacks`) |
| `--full-text` | `-f` | false | Also download full article text + comments in parallel |
| `--full-text-only` | | false | Skip archive page scrape, only download full texts for existing articles |
| `--metadata-only` | | false | Skip full text download, only scrape archive page metadata (titles, dates, excerpts) |
| `--since YYYY-MM-DD` | | | Only process articles newer than this date |
| `--until YYYY-MM-DD` | | | Scrape from newest until this cutoff date (stops when all articles on a page are older) |
| `--reset` | | false | Delete all existing data for this category before scraping (requires confirmation) |
| `--skip-comments` | | false | Skip parsing comments during full text download |
| `--max-pages N` | | all | Stop after N archive pages (from newest to oldest) |
| `--dry-run` | | false | Fetch only the first archive page, validate, print report — does NOT save to DB |

### Information options

| Flag | Requires | Description |
|------|----------|-------------|
| `--info` | optional `-c` | Show scrape status (all categories or specific category) |
| `--list-categories` | | Fetch and display available Hackaday categories |
| `--latest N` | `-c` | Show N most recent articles (title, date, tags, excerpt, URL) |
| `--since-date` | `-c` | Print the latest article date (`YYYY-MM-DD` or `NONE`) for incremental scraping |

### Database query options (read-only, safe)

| Flag | Requires | Description |
|------|----------|-------------|
| `--db-schema` | | Show database schema — tables, columns, types |
| `--db-summary` | optional `-c` | Show summary of stored data (article count, date range, sessions) |
| `--db-search KEYWORD` | optional `-c` | Search articles by keyword in title, excerpt, and content |
| `--json` | any `--db-*` | Output results as JSON instead of formatted table |

### Search options

| Flag | Requires | Description |
|------|----------|-------------|
| `--search "<text>"` | `-c` | Ad-hoc semantic search |
| `--query-file <path>` | `-c` | Search by persistent query file |
| `--top N` | | Limit results (default: 10) |
| `--min-total N` | | Minimum total score threshold |

Advanced pipeline access:

| Flag | Description |
|------|-------------|
| `--search-candidates --stage filter\|rerank --batch N --json` | Read a batch of candidates |
| `--search-save <file> --stage filter\|rerank` | Save subagent results from file |
| `--search-save-stdin --stage filter\|rerank` | Save subagent results from stdin |
| `--search-status -c <slug> --query-file <path>` | Show analysis status |
| `--search-report -c <slug> --query-file <path> --top N` | Report from cache |
| `--search-skip-filter -c <slug> --query-file <path>` | Skip triage stage |

### Trend Analysis options

| Flag | Requires | Description |
|------|----------|-------------|
| `--trends` | `-c` | Full trend analysis over period |
| `--trend-keyword <word>` | with `--trends` | Focus on a keyword |
| `--save-trend-interpretation <hash> <text>` | | Cache LLM interpretation |

### Interest Digest options

| Flag | Requires | Description |
|------|----------|-------------|
| `--digest` | `-c` | Generate digest by interest files |
| `--interests-dir <path>` | with `--digest` | Custom interests directory |

### Batch Summarization options

| Flag | Requires | Description |
|------|----------|-------------|
| `--summarize-status` | `-c` | Show how many articles lack summary_ru |
| `--summarize-candidates --batch N --json` | `-c` | Read a batch for summarization |
| `--summarize-save <file>` | `-c` | Save subagent summaries from file |

### Export options

| Flag | Requires | Description |
|------|----------|-------------|
| `--export-json` | `-c` | Export articles to `data/<category>.json` |
| `--since YYYY-MM-DD` | with `--export-json` | Optional date filter for export |

### Configuration

| Flag | Description |
|------|-------------|
| `--workers N` | Parallel workers for full text download (default: 10) |
| `--delay MIN MAX` | Request delay range in seconds |
| `--timeout SECONDS` | Request timeout in seconds |
| `--output, -o DIR` | Output directory for exports (default: `data`) |
| `--db PATH` | Path to SQLite database (default: `data/hackaday.db`) |
| `--verbose, -v` | Debug logging |

## Usage scenarios

### First scrape — full archive with full text
```powershell
python src/main.py -c led-hacks --full-text
```

### First scrape — metadata only (fast)
```powershell
python src/main.py -c led-hacks --metadata-only
```

### Incremental update (fetch new articles only)
```powershell
python src/main.py --since-date -c led-hacks    # get latest date
python src/main.py -c led-hacks --since 2025-01-01
```

### Scrape from newest until cutoff date (fill history)
```powershell
python src/main.py -c led-hacks --until 2024-06-01
```

### Resume interrupted scrape
```powershell
python src/main.py -c led-hacks
```

### N newest pages
```powershell
python src/main.py -c led-hacks --max-pages 3
```

### Dry run (validate before saving)
```powershell
python src/main.py -c led-hacks --dry-run
```

### Check database status
```powershell
python src/main.py --db-summary
python src/main.py --db-summary -c led-hacks
```

### Semantic search
```powershell
python src/main.py --search "LED cube with ESP32" -c led-hacks --top 10
```

### Trend analysis
```powershell
python src/main.py --trends -c led-hacks --since 2025-01-01
```

### Interest digest
```powershell
python src/main.py --digest -c led-hacks --since 2025-06-20 --until 2025-06-26
```

### Reset and re-scrape
```powershell
python src/main.py -c led-hacks --reset
```

### Export to JSON
```powershell
python src/main.py -c led-hacks --export-json
python src/main.py -c led-hacks --export-json --since 2025-01-01
```

## Output format

### Table output (default)
```
Articles: 42
Full texts: 30
Date range: 2024-03-15 — 2025-06-01
```

### JSON output (with `--json`)
```json
{
  "category": "led-hacks",
  "info": { "total_articles": 42, "full_text_count": 30, ... }
}
```

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (invalid args, network, DB) |
| 130 | Interrupted by user (Ctrl+C) |

## Database

SQLite at `data/hackaday.db`. Tables:
- `articles` — article metadata + content + summary_ru
- `comments` — article comments
- `scrape_sessions` — scrape session tracking
- `pages` — per-page scrape progress
- `search_scores` — search cache (query hashes, filter status, scores)
- `trend_cache` — LLM interpretation cache