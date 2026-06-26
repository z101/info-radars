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
| `--db-query SQL` | | Execute an arbitrary SELECT query; only SELECT statements allowed |
| `--json` | any `--db-*` | Output results as JSON instead of formatted table |

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
Stops when all articles on a page are older than `2024-06-01`. Useful for grabbing a specific time window.

### Combine since + until (narrow window)
```powershell
python src/main.py -c led-hacks --since 2024-01-01 --until 2024-06-01
```

### Resume interrupted scrape
```powershell
python src/main.py -c led-hacks
```
Scraper resumes by skipping already-scraped pages.

### N newest pages
```powershell
python src/main.py -c led-hacks --max-pages 3
```
Scrapes only the 3 most recent archive pages (articles sorted newest to oldest).

### Dry run (validate before saving)
```powershell
python src/main.py -c led-hacks --dry-run
```

### Check database status
```powershell
python src/main.py --db-summary
python src/main.py --db-summary -c led-hacks
```

### Query database
```powershell
python src/main.py --db-schema
python src/main.py --db-query "SELECT title, date FROM articles WHERE category='led-hacks' LIMIT 5"
python src/main.py --db-search "ESP32" -c led-hacks
python src/main.py --db-query "SELECT COUNT(*) as cnt FROM comments" --json
```

### Export to JSON
```powershell
python src/main.py -c led-hacks --export-json
python src/main.py -c led-hacks --export-json --since 2025-01-01
```

### Reset and re-scrape
```powershell
python src/main.py -c led-hacks --reset
```
Prompts for confirmation before deleting.

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
- `articles` — article metadata + content
- `comments` — article comments
- `scrape_sessions` — scrape session tracking
- `pages` — per-page scrape progress
- `search_scores` — search cache (query hashes, filter status, scores)