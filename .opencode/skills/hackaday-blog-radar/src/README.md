# Hackaday Radar CLI

CLI for scraping and analyzing articles from hackaday.com. Run commands from the skill directory.

## Quick start

```powershell
..\..\..\.venv\Scripts\activate
python src/main.py --category led-hacks --full-text
```

## Global flags

These work in all modes (before any subcommand):

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--category <slug>` | `-c` | | Category slug (e.g. `led-hacks`, `3d-printing-hacks`) |
| `--verbose` | `-v` | false | Debug logging |
| `--json` | | false | Output as JSON |
| `--db PATH` | | `data/hackaday.db` | Path to SQLite database |
| `--output, -o DIR` | | `data` | Output directory for exports |
| `--workers N` | | 10 | Parallel workers for full text download |
| `--delay MIN MAX` | | 0.5-1.0s | Request delay range |
| `--timeout SEC` | | 30 | Request timeout |
| `--top N` | | | Limit report/display to top N |
| `--min-total N` | | 0 | Minimum total score threshold |
| `--batch-size N` | | 100 | Batch size for candidates |

## Subcommands

### `search` — Semantic search via searcher subagents

| Command | Description |
|---------|-------------|
| `search init --query-file <path> -c <slug>` | Initialize search session, show batch count |
| `search get-batch INDEX --query-file <path> -c <slug>` | Get batch JSON for searcher subagent |
| `search set-batch --query-file <path> [--batch-file <f> ...]` | Save scored results (stdin fallback) |
| `search status --query-file <path> -c <slug>` | Show search progress (scored/pending) |
| `search report --query-file <path> -c <slug> [--top N] [--min-score N]` | Generate XLSX report with normalized scores |

**Examples:**
```powershell
# Init — check status and batch count
python src/main.py search init --query-file ../../../queries/led_sculptures.md -c led-hacks

# Get batch 0 for searcher subagent
python src/main.py search get-batch 0 --query-file ../../../queries/led_sculptures.md -c led-hacks --batch-size 100

# Save scored results from file
python src/main.py search set-batch --query-file ../../../queries/led_sculptures.md --batch-file scored_batch_0.json

# Status
python src/main.py search status --query-file ../../../queries/led_sculptures.md -c led-hacks

# Report (XLSX with MinMax normalized scores)
python src/main.py search report --query-file ../../../queries/led_sculptures.md -c led-hacks --top 10
```

**Pipeline:** Single-stage scoring (0-100) + MinMax normalization. No filter/rerank stages.

### `track` — Trend analysis and interest digest

| Command | Description |
|---------|-------------|
| `track trends -c <slug> [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--keyword KW]` | Analyze trends over a period |
| `track digest -c <slug> [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--interests-dir PATH]` | Generate digest from interest files |
| `track save-interpretation -c <slug> <HASH> <TEXT>` | Cache LLM trend interpretation |

**Examples:**
```powershell
# Trend analysis
python src/main.py track trends -c led-hacks --since 2025-01-01

# Focus on keyword
python src/main.py track trends -c led-hacks --since 2025-01-01 --keyword ESP32

# Interest digest
python src/main.py track digest -c led-hacks --since 2025-06-20 --until 2025-06-26

# Save LLM interpretation
python src/main.py track save-interpretation -c led-hacks abc123 "interpretation text"
```

### `summarize` — Batch article summarization

| Command | Description |
|---------|-------------|
| `summarize status -c <slug>` | Show summarization progress |
| `summarize candidates -c <slug> [--batch N] [--batch-size N]` | Read a batch for summarization |
| `summarize save <path> -c <slug>` | Save subagent summaries from JSON file |

**Examples:**
```powershell
# Status
python src/main.py summarize status -c led-hacks

# Candidates for batch 0
python src/main.py summarize candidates -c led-hacks --batch 0 --json

# Save results
python src/main.py summarize save results.json -c led-hacks
```

## Flat flags (no subcommand — scraping + info + interesting/read)

### Scraping options

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--full-text` | `-f` | false | Also download full article text + comments in parallel |
| `--full-text-only` | | false | Skip archive page scrape, only download full texts |
| `--metadata-only` | | false | Skip full text download, only scrape metadata |
| `--since YYYY-MM-DD` | | | Only process articles newer than this date |
| `--until YYYY-MM-DD` | | | Scrape from newest until this cutoff date |
| `--reset` | | false | Delete all data for this category (requires confirmation) |
| `--skip-comments` | | false | Skip parsing comments during full text download |
| `--max-pages N` | | all | Stop after N archive pages |
| `--dry-run` | | false | Validate first page only — no save |

### Information options

| Flag | Requires | Description |
|------|----------|-------------|
| `--info` | optional `-c` | Show scrape status |
| `--list-categories` | | Fetch and display available categories |
| `--latest N` | `-c` | Show N most recent articles |
| `--since-date` | `-c` | Print latest article date (`YYYY-MM-DD` or `NONE`) |
| `--export-json` | `-c` | Export articles to JSON |
| `--db-schema` | | Show database schema |
| `--db-summary` | optional `-c` | Show summary of stored data |
| `--db-search KEYWORD` | optional `-c` | Search articles by keyword |
| `--search "<text>"` | `-c` | Ad-hoc semantic search |

### Interesting / Read flags

| Flag | Requires | Description |
|------|----------|-------------|
| `--mark-interesting <id> [id ...]` | | Mark article(s) as interesting |
| `--unmark-interesting <id> [id ...]` | | Unmark article(s) as interesting |
| `--mark-read <id> [id ...]` | | Mark article(s) as read |
| `--unmark-read <id> [id ...]` | | Unmark article(s) as read |
| `--list-interesting` | `-c` | List interesting articles |
| `--list-unread` | `-c` | List unread articles |
| `--export-xlsx` | `-c` | Export articles to Excel |
| `--import-xlsx <path>` | | Import article flags from Excel file |
| `--filter <mode>` | with `--export-xlsx` | Filter: `all` (default), `unread`, `interesting` |

## Usage scenarios

### First scrape — full archive with full text
```powershell
python src/main.py -c led-hacks --full-text
```

### First scrape — metadata only (fast)
```powershell
python src/main.py -c led-hacks --metadata-only
```

### Incremental update
```powershell
python src/main.py --since-date -c led-hacks
python src/main.py -c led-hacks --since 2025-01-01
```

### Scrape from newest until cutoff date
```powershell
python src/main.py -c led-hacks --until 2024-06-01
```

### Dry run
```powershell
python src/main.py -c led-hacks --dry-run
```

### Ad-hoc semantic search
```powershell
python src/main.py --search "LED cube with ESP32" -c led-hacks --top 10
```

### Orchestrated semantic search
```powershell
python src/main.py search init --query-file ../../../queries/led_sculptures.md -c led-hacks
# spawn searcher subagents for each batch, then:
python src/main.py search set-batch --query-file ../../../queries/led_sculptures.md --batch-file <results>
python src/main.py search report --query-file ../../../queries/led_sculptures.md -c led-hacks --top 10
```

### Reset and re-scrape
```powershell
python src/main.py -c led-hacks --reset
```

### Export/Import flags
```powershell
python src/main.py --export-xlsx -c led-hacks --filter unread
python src/main.py --import-xlsx reports/hackaday-blog-radar/articles.xlsx
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
{ "category": "led-hacks", "info": { "total_articles": 42, ... } }
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
- `search_scores` — search cache (query hashes, scores, content_hash)
- `trend_cache` — LLM interpretation cache

## Utility scripts

### `src/analyzer/format_batch_prompt.py`

Formats a candidates JSON file into a search prompt for LLM subagents:

```powershell
..\..\..\.venv\Scripts\python src\analyzer\format_batch_prompt.py --candidates <file> --query <file> --output <file>
```

### `src/analyzer/normalizer.py`

MinMax normalizes scores to 0-100 range. Used automatically in search reports.