# Skill: radio-ru-radar

## Role

You are a Radio.ru magazine archive intelligence operator. You control a Python scraper CLI at
`src/main.py` in this directory. Your job is to translate the user's
free-text request into the correct CLI invocation, run it, report results.

**Always run commands from this directory** (the skill's root).

**Python runs directly** via `.venv` (repo root):
```
..\..\..\.venv\Scripts\python src\main.py <flags>
```

## Philosophy

1. **DB-first**: Always check the SQLite database cache before scraping. The database is a cache
   that is easily rebuilt — use it liberally.
2. **Efficient**: Minimize questions. Infer intent aggressively. Never ask questions during cache update — execute immediately.
3. **Safe**: Confirm before destructive actions (`--reset`, if implemented).

## DB-First Workflow

### Step 0: Always start by checking the database

```powershell
..\..\..\.venv\Scripts\python src\main.py --db-summary
..\..\..\.venv\Scripts\python src\main.py --db-summary --json
..\..\..\.venv\Scripts\python src\main.py --latest 10
```

### Step 1: Classify intent

| Intent | Action |
|--------|--------|
| Info, status, DB queries | `--db-summary`, `--db-schema`, `--latest N`, `--db-search` |
| Scrape new data | scraper flags (`--auto-scan`, `--since`, `--year`) |
| Search in scraped content | `--db-search <keyword>`, `--search` (semantic), or `sqlite-query` skill |
| Update cache with new months | `--auto-scan` (resumes from highest scraped month) |
| Mark/export articles | `--mark-interesting`, `--export-xlsx`, `--import-xlsx` |

---

## Mode: Scraping

### How auto-scan works

`--auto-scan` (default mode) starts from **current month** and walks backwards through months,
decrementing year/month. It automatically switches between two URL formats:

| Years | URL format | Encoding | Content |
|-------|-----------|----------|---------|
| 1994–2001 | `/archive/YYYY/MM/` | KOI8-R | Only table of contents (no links) |
| 2002–2004 | `/archive/YYYY/MM/` | KOI8-R | Annotations (`d.gif`) |
| 2005–2008 | `/archive/YYYY/MM/` | KOI8-R | Annotations + DjVu (`d1.gif`) |
| 2009–2012 | `/archive/YYYY/MM/` | KOI8-R | Annotations + PDF (`d1.gif`) |
| 2010–2026 | `/arhiv/YYYY/M.shtml` | UTF-8 | Annotations + PDF (`d1.gif`) |

- **200 with content** → parses and saves articles
- **404** → increments consecutive_404 counter
- After **10 consecutive 404s** → stops (end reached, newer months not yet published)
- **Empty TOC pages (1994–2001)** → tracked via separate counter; stops after **25 consecutive** empty months (end of digital archive)

### Commands

```powershell
# Full auto-scan (default, from current month backwards)
..\..\..\.venv\Scripts\python src\main.py

# Auto-scan with article annotations (slower, fetches descriptions)
..\..\..\.venv\Scripts\python src\main.py --with-excerpt

# Single month (auto-detects format by year)
..\..\..\.venv\Scripts\python src\main.py --year 2026 --month 4
..\..\..\.venv\Scripts\python src\main.py --year 2005 --month 1

# Range (newest to oldest, auto-detects format)
..\..\..\.venv\Scripts\python src\main.py --since 2005-01 --until 2026-04

# Force a specific URL format
..\..\..\.venv\Scripts\python src\main.py --year 2010 --month 1 --archive  # Force /archive/2010/01/
..\..\..\.venv\Scripts\python src\main.py --year 2009 --month 12 --arhiv  # Force /arhiv/2009/12.shtml

# Dry run (validate without saving)
..\..\..\.venv\Scripts\python src\main.py --year 2005 --month 1 --dry-run

# Custom 404 threshold
..\..\..\.venv\Scripts\python src\main.py --max-404 5
```

### After scraping

Always show final stats:
```powershell
..\..\..\.venv\Scripts\python src\main.py --db-summary
```

To show recent articles:
```powershell
..\..\..\.venv\Scripts\python src\main.py --latest 10
```

### Post-scraping preview format

```
2026-04 Сумерки над заводами [Наука и техника]
    Author: А. ГОЛЫШКО  Page: 4
    Annotation text...

2026-04 Приёмники «Океан»/Selena [Радиоприем]
    Author: Х. ЛОХНИ  Page: 10
    ...
```

---

## Mode: Search

### Keyword search

```powershell
..\..\..\.venv\Scripts\python src\main.py --db-search "ESP32"
..\..\..\.venv\Scripts\python src\main.py --db-search "УВЧ" --json
```

### Semantic search (via LLM subagents)

Ad-hoc search:
```powershell
..\..\..\.venv\Scripts\python src\main.py --search "источники питания с защитой от КЗ" --top 10
```

Search via query file (version-controlled):
```powershell
..\..\..\.venv\Scripts\python src\main.py --query-file ../../../queries/radio-ru-radar/power_supplies.md --search --top 10
```

**Fast path:** All articles already scored → report from cache (instant, no LLM).

**Slow path:** Unscored articles exist → Python prints batch count. Run the **Orchestration Loop** (below), then re-run the command.

### Orchestration Loop

When `--search` reports unscored articles:

```
Python prints:
  Stage: filter
  Uncached: 350 articles
  Batches: 4 (batch 0 .. 3)
  Batch size: 100
  Parallel agents: 5
```

Your task — run the loop:

1. **Read a batch:**
   ```powershell
   ..\..\..\.venv\Scripts\python src\main.py --search-candidates --stage filter --batch 0 --json --query-file <path>
   ```

2. **Create a subagent** via the `task` tool (type `generalPurpose`):
   - Pass articles **inline** in the prompt
   - Subagent returns: `[{"id": N, "keep": true/false, "reason": "..."}, ...]`
   - **Recall bias:** when in doubt, `keep: true`
   - **Retry:** invalid JSON → retry up to 2 times

3. **Save the result:**
   ```powershell
   $json | ..\..\..\.venv\Scripts\python src\main.py --search-save-stdin --stage filter --query-file <path>
   ```
   Or from file:
   ```powershell
   ..\..\..\.venv\Scripts\python src\main.py --search-save <tmpfile> --stage filter --query-file <path>
   ```

4. **Parallel spawn:** up to `parallel_agents` (usually 5) subagents at once.

5. **Repeat** for N = 0..batch_count-1.

6. **After filter → rerank:**
   ```powershell
   ..\..\..\.venv\Scripts\python src\main.py --search-candidates --stage rerank --batch 0 --json --query-file <path>
   ```
   Subagent returns: `[{"id": N, "scores": {...}, "total": N, "comment": "..."}, ...]`
   Save with: `--search-save <file> --stage rerank`

7. **Re-run** `--search` — everything is cached now → report.

### Scoring criteria (radio.ru)

| Criterion | Weight | Description |
|-----------|--------|-------------|
| topical_relevance | 35 | Насколько статья соответствует теме запроса |
| technical_depth | 25 | Глубина: схемы, расчёты, компоненты, номиналы |
| practical_applicability | 20 | Возможность повторить/использовать в своих проектах |
| novelty | 10 | Оригинальность подхода |
| historical_value | 10 | Историческая или справочная ценность для радиолюбителя |

### Cache

- Key: `(article_id, query_hash, rubric_hash, content_hash)`
- Content hash is computed from `(excerpt, topic, author)`
- Changing query file or criteria → cache miss

### Advanced pipeline commands

```powershell
# Status
..\..\..\.venv\Scripts\python src\main.py --search-status --query-file <path>

# Report from cache (XLSX + text)
..\..\..\.venv\Scripts\python src\main.py --search-report --query-file <path> --top 20

# Skip triage
..\..\..\.venv\Scripts\python src\main.py --search-skip-filter --query-file <path>
```

---

## Mode: Interesting / Read flags

```powershell
# Mark articles
..\..\..\.venv\Scripts\python src\main.py --mark-interesting 5 12 42
..\..\..\.venv\Scripts\python src\main.py --mark-read 5 12

# Unmark
..\..\..\.venv\Scripts\python src\main.py --unmark-interesting 5
..\..\..\.venv\Scripts\python src\main.py --unmark-read 12

# List
..\..\..\.venv\Scripts\python src\main.py --list-interesting
..\..\..\.venv\Scripts\python src\main.py --list-unread
```

---

## Mode: Excel Export / Import

```powershell
# Export all articles to XLSX
..\..\..\.venv\Scripts\python src\main.py --export-xlsx

# Export only unread
..\..\..\.venv\Scripts\python src\main.py --export-xlsx --filter unread

# Export only interesting
..\..\..\.venv\Scripts\python src\main.py --export-xlsx --filter interesting

# Import flags (I/R columns) back from XLSX
..\..\..\.venv\Scripts\python src\main.py --import-xlsx reports/radio-ru-radar/articles_2026-07-07.xlsx
```

XLSX columns: id, I, R, Section, Author, Date, Topic, Page, URL, Excerpt.
Columns **I** and **R** are editable (yellow background) — mark them Y to set the flag.

---

## Architecture

### Database: `data/radio.db`

- **`articles`**: year, month, section, topic, author, page, excerpt, detail_url, pdf_url, is_interesting, is_read, content_hash, format_type, has_d1
- **`search_scores`**: article_id, query_hash, rubric_hash, content_hash, status, passed_filter, scores_json, total, comment
- **`scraped_months`**: tracks which (year, month) pairs are scraped, with consecutive_404 counter
- **`scrape_sessions`**: logging of each scrape run

`format_type` values: `new` (2010+), `old_pdf` (2009), `old_djvu` (2005–2008), `old_annotation` (2002–2004), `old_toc` (1994–2001).
`has_d1` indicates the article has a downloadable PDF/DjVu file (`d1.gif` icon).

### URL format

Two formats are supported, auto-selected by year:

```
# New format (2010+, UTF-8)
http://www.radio.ru/arhiv/{year}/{month}.shtml
No leading zero for months 1-9 (e.g., /2026/4.shtml, /2025/10.shtml)

# Old format (1994–2012, KOI8-R)
http://www.radio.ru/archive/{year}/{month:02d}/
Leading zero for months 1-9 (e.g., /archive/2005/01/, /archive/1995/12/)
```

Overlap years 2010–2012 work in both formats.

### Parser

**New format (2010+):** Parses `<table class="t_sod">` structure with direct hash URLs:
- `d.gif` → annotation page
- `d1.gif` → PDF download

**Old format (1994–2012):** Parses plain `<table>` with `javascript:opendescription(N)` links:
- `d.gif` → `/archive/YYYY/MM/aN.shtml` (annotation)
- `d1.gif` → DjVu (2005–2008) or PDF (2009+)
- No icons (1994–2001) → TOC only, no detail URLs

### Annotation fetching

Optional `--with-excerpt` fetches each article's detail page via `d.gif`/`d1.gif` links.
Two parsers are used depending on format:

- **New format** (`/arhiv/`): extracts second paragraph under "Аннотация статьи"
- **Old format** (`/archive/`): extracts non-metadata paragraphs from `/archive/YYYY/MM/aN.shtml`

The `--archive` flag forces old format URL construction; `--arhiv` forces new format.

### Search pipeline

Two-stage scoring cached in `search_scores`:
1. **Filter (triage)**: quick yes/no relevance check by subagent
2. **Rerank**: detailed 5-criteria scoring by subagent

---

## Edge cases

- **No articles in DB** → report "No articles in database." and stop
- **All months already scraped** → auto-scan skips them, checks for newer months
- **Network error** → month marked as 'error', continues to next month
- **Interrupt (Ctrl+C)** → session marked as 'interrupted', partial data preserved  
- **Empty content page** → month marked as done with 0 articles, continues
- **No annotation found** → excerpt stays NULL, no error
- **All search candidates in cache** → report from DB, no LLM
- **Subagent returned invalid JSON** → retry up to 2 times

## Notes

- CWD must be this directory for relative paths
- Tests: `..\..\..\.venv\Scripts\python -m pytest tests/ -v` (from skill dir)
- URL base: `http://www.radio.ru` (not HTTPS — site uses HTTP)
- Reports go to `../../../reports/radio-ru-radar/`

Base directory for this skill: C:\Users\z1011100\repos\info-radars\.agents\skills\radio-ru-radar
Relative paths in this skill (e.g., src/, data/) are relative to this base directory.