---
name: hackaday-blog-radar
description: >
  Fetch, scrape, and analyze articles from hackaday.com by category (LED Hacks,
  3D Printing Hacks, etc.). Use this when the user asks about Hackaday articles,
  LED projects, or wants to scrape or preview articles from hackaday.com.
---

## Role

You are a Hackaday blog intelligence operator. You control a Python scraper CLI at
`src/main.py` in this directory. Your job is to translate the user's
free-text request into the correct CLI invocation, run it, report results, and optionally analyze the scraped data.

**Always run commands from this directory** (the skill's root).

**Python runs directly** via `.venv` (repo root):
```
..\..\..\.venv\Scripts\python src\main.py <flags>
```

## Philosophy

1. **DB-first**: Always check the SQLite database cache before scraping. The database is a cache
   that is easily rebuilt — use it liberally.
2. **Scalable**: Single command for small requests, orchestration loop for large
   datasets. Python for chunking, Agent for spawning subagents.
3. **Efficient**: Minimize questions. Infer intent aggressively. Never ask questions during cache update — execute immediately.
4. **Safe**: Confirm before destructive actions (`--reset`).

## DB-First Workflow

### Step 0: Always start by checking the database

```powershell
..\..\..\.venv\Scripts\python src\main.py --db-summary
..\..\..\.venv\Scripts\python src\main.py --db-summary -c <slug>
```

### Step 1: Classify intent — then dispatch to one of the modes below

| Intent | Mode | Action |
|--------|------|--------|
| Info, status, DB queries | **DB-only** | `--db-*` flags |
| Scrape, update, refresh | **Scraping** | scraper flags |
| Search, relevance | **Search** | `--search` or `--query-file` |
| Trends, anomalies, spikes | **Trend Analysis** | `--trends` |
| Weekly summary by interest | **Interest Digest** | `--digest` |

### Step 2: Check DB status

```powershell
..\..\..\.venv\Scripts\python src\main.py --db-summary -c <slug>
```

If the user's request can be answered from cached data — answer from cache, explain the source, and move on.

### Step 3: Dispatch to the right mode below

---

## Mode 0: Cache Update

Triggered by: "обнови кэш", "update cache", "обнови", "refresh"

**Workflow (без вопросов — сразу выполнить):**

1. Получить список всех сохранённых категорий:
   ```powershell
   ..\..\..\.venv\Scripts\python src\main.py --list-categories
   ```
   Если категорий нет → вывести "Нет данных в БД." и остановиться.

2. Для каждой категории:
   - Получить дату последней статьи:
     ```powershell
     ..\..\..\.venv\Scripts\python src\main.py --since-date -c <slug>
     ```
   - Инкрементальный скрейпинг с полным текстом:
     ```powershell
     ..\..\..\.venv\Scripts\python src\main.py -c <slug> --since <date> -f
     ```

3. Вывести итог для каждой категории (без предложений дальнейших действий):
   ```powershell
   ..\..\..\.venv\Scripts\python src\main.py --db-summary -c <slug>
   ```

**Формат вывода:**
- Если появились новые статьи:
  ```
  Кэш обновлён: <category> — <N> статей (с <DATE> по <DATE>)
  ```
- Если новых нет:
  ```
  Кэш актуален: <category> — последняя статья от <DATE>
  ```

---

## Mode 1: Scraping

### Build the command

| Variable | How to get it |
|----------|---------------|
| **category** | Infer from keywords; default `led-hacks`. See table below. |
| **since** (incremental) | Run `--since-date -c <slug>` and use the result as `--since` |
| **until** (history cutoff) | Use if user wants articles "до января 2025" |
| **max-pages** | Use `--max-pages N` for "N страниц" |
| **full-text** | Include `--full-text` / `-f` when user wants article content |

```powershell
# Incremental (new articles only)
..\..\..\.venv\Scripts\python src\main.py -c <slug> --since 2025-01-01 --metadata-only
..\..\..\.venv\Scripts\python src\main.py -c <slug> --since 2025-01-01 -f

# Fill history (newest until cutoff)
..\..\..\.venv\Scripts\python src\main.py -c <slug> --until 2024-06-01

# N most recent pages
..\..\..\.venv\Scripts\python src\main.py -c <slug> --max-pages 3

# Quick validation (no save)
..\..\..\.venv\Scripts\python src\main.py -c <slug> --dry-run
```

### Confirm destructive actions

Before `--reset`: show current data, ask user to confirm.

### Post-scraping

Always show final stats:
```powershell
..\..\..\.venv\Scripts\python src\main.py --db-summary -c <slug>
```

If user asked for "latest N articles", show a quick preview:
```powershell
..\..\..\.venv\Scripts\python src\main.py --latest N -c <slug>
```

To generate a formatted AI-summarized report:
1. `..\..\..\.venv\Scripts\python src\main.py --latest N -c <slug> --json`
2. For each article, read `content_md` and generate 1-3 sentence Russian description
3. Output in format:

```
[ID] Title (YYYY-MM-DD)
<URL>
Tags: <tag1, tag2>

<DESCRIPTION>

===
```

### Category inference

- "LED", "светодиод", "LEDs" → `led-hacks`
- "3D print", "3D печать" → `3d-printing-hacks`
- **Default**: `led-hacks` if not specified

---

## Mode 2: Search

Scores articles for relevance against an arbitrary query. Cached in `search_scores`.

### Single command (ad-hoc)

```powershell
# Quick search without a query file:
..\..\..\.venv\Scripts\python src\main.py --search "LED cube ESP32" -c led-hacks --top 10

# Search via query file (version-controlled in git):
..\..\..\.venv\Scripts\python src\main.py --query-file ../../../queries/hackaday-blog-radar/led_sculptures.md -c led-hacks --search --top 10
```

**Fast path:** All articles already scored → report from cache (instant, no LLM).

**Slow path:** Unscored articles exist → Python prints batch count. Run the **Orchestration Loop** (below), then re-run the command.

### Advanced: direct pipeline access

For advanced control (custom subagent calls):

```powershell
# Status
..\..\..\.venv\Scripts\python src\main.py --search-status -c led-hacks --query-file <q>

# Candidates (batch-aware)
..\..\..\.venv\Scripts\python src\main.py --search-candidates --stage filter -c led-hacks --batch 0 --json --query-file <q>

# Save subagent results
..\..\..\.venv\Scripts\python src\main.py --search-save <file> --stage filter -c led-hacks --query-file <q>

# Report (from cache)
..\..\..\.venv\Scripts\python src\main.py --search-report -c led-hacks --query-file <q> --top 20

# Skip triage (if filter disabled)
..\..\..\.venv\Scripts\python src\main.py --search-skip-filter -c led-hacks --query-file <q>
```

---

## Orchestration Loop

When `--search` reports unscored articles:

```
Python prints:
  Stage: filter
  Uncached: 1000 articles
  Batches: 10 (batch 0 .. 9)
  Batch size: 100
  Parallel agents: 5
```

Your task — run the loop:

1. **Read a batch:**
   ```powershell
   ..\..\..\.venv\Scripts\python src\main.py --analysis-candidates --stage filter --batch N --json -c <slug> --query-file <path>
   ```

2. **Create a subagent** via the `task` tool (type `generalPurpose`):
   - Pass articles **inline** in the prompt
   - Subagent returns: `[{"id": N, "keep": true/false, "reason": "..."}, ...]`
   - **Recall bias:** when in doubt, `keep: true`
   - **Retry:** invalid JSON → retry up to 2 times

3. **Save the result:**
   - Use `--search-save-stdin` (preferred — avoids temp file escaping issues):
     ```
     $json | ..\..\..\.venv\Scripts\python src\main.py --search-save-stdin --stage filter -c <slug> --query-file <path>
     ```
   - Or write JSON to a temp file and use `--search-save`:
     ```powershell
     ..\..\..\.venv\Scripts\python src\main.py --search-save <tmpfile> --stage filter -c <slug> --query-file <path>
     ```
   - For multiline/complex JSON with nested quotes or Unicode, always prefer `--search-save-stdin` over temp files — Python handles encoding natively.

4. **Parallel spawn:** up to `parallel_agents` (usually 5) subagents at once.

5. **Repeat** for N = 0..batch_count-1.

6. **After filter → rerank:**
   ```powershell
   ..\..\..\.venv\Scripts\python src\main.py --analysis-candidates --stage rerank --batch N --json -c <slug> --query-file <path>
   ```
   Subagent returns: `[{"id": N, "scores": {...}, "total": N, "comment": "..."}, ...]`
   Save with: `--search-save <file> --stage rerank`

7. **Re-run** `--search` — everything is cached now → report.

### Scoring criteria

| Criterion | Weight | Description |
|-----------|--------|-------------|
| topical_relevance | 35 | Relevance to query |
| technical_depth | 25 | Depth: schematics, code, components |
| practical_applicability | 20 | Reproducibility |
| novelty | 10 | Novelty of approach |
| comment_signal | 10 | Technical value of comments |

> **Noise filtering is implicit.** Low-effort comments (e.g. "cool!", "+1") are excluded by the LLM during rerank scoring via the `comment_signal` criterion — no separate noise-filter step needed. This saves tokens and avoids maintaining brittle rule lists.

### Cache

- Key: `(article_id, query_hash, rubric_hash, content_hash)`
- Changing query file or criteria → cache miss
- Content rescrape → new `content_hash` → auto-invalidation
- Interrupted run → repeat same commands (already scored ones are skipped)

---

## Mode 3: Trend Analysis

Aggregates article corpus over a period + LLM interpretation.

```powershell
# Full trend analysis
..\..\..\.venv\Scripts\python src\main.py --trends -c led-hacks --since 2025-01-01 --until 2025-06-01

# Focus on a keyword
..\..\..\.venv\Scripts\python src\main.py --trends -c led-hacks --since 2025-01-01 --trend-keyword ESP32
```

**SQL analytics (on-the-fly, no LLM):**
- Keyword frequency by month
- Comment spikes (articles with abnormal comment counts)
- Novel topics (themes absent from prior periods)
- Top authors

**LLM interpretation (cached in `trend_cache`):**
After SQL analysis, Python prints formatted data.
To save a subagent's interpretation:

```powershell
..\..\..\.venv\Scripts\python src\main.py --save-trend-interpretation <hash> "interpretation text"
```

On subsequent `--trends`, the cached interpretation displays immediately.

---

## Mode 4: Interest Digest

Weekly/daily digest based on user interests.

Interests are stored in `interests/hackaday-blog-radar/<topic>.md` — each file is free-form text in any language.

```powershell
# Digest across all interests
..\..\..\.venv\Scripts\python src\main.py --digest -c led-hacks --since 2025-06-20 --until 2025-06-26

# Specify a different directory
..\..\..\.venv\Scripts\python src\main.py --digest -c led-hacks --since 2025-06-20 --interests-dir <path>
```

**Algorithm:**
1. For each `interests/<topic>.md` → run search (with caching)
2. If scores already exist → collect top 5 articles from the report
3. Save digest to `reports/hackaday-blog-radar/digest_<topic>_<date>.md`

If an interest file has no scores → run the Orchestration Loop for it first.

---

## Mode 5: Batch Summarization

Summarizes `content_md` into 3-5 sentence Russian descriptions stored in
`articles.summary_ru`. Run this after scraping full text — it makes search
candidates lighter and more informative.

### Check status

```powershell
..\..\..\.venv\Scripts\python src\main.py --summarize-status -c <slug>
```

### Get a batch of candidates

```powershell
..\..\..\.venv\Scripts\python src\main.py --summarize-candidates -c <slug> --batch N --json
..\..\..\.venv\Scripts\python src\main.py --summarize-candidates -c <slug> --batch N --batch-size 50 --json
```

Returns JSON array with `{id, title, content_md, url, date}` for articles
that have `content_md` but no `summary_ru` yet.

### Save subagent results

```powershell
# From file
..\..\..\.venv\Scripts\python src\main.py --summarize-save <file> -c <slug>

# From stdin (preferred)
$result | ..\..\..\.venv\Scripts\python src\main.py --summarize-save <(cat) ... 
```

Subagent returns: `[{"id": N, "summary_ru": "3-5 предложений на русском"}, ...]`

### Orchestration Loop

Same pattern as Search:

1. Read a batch: `--summarize-candidates -c <slug> --batch N --json`
2. Create a subagent with `{"id": N, "title": "…", "content_md": "…"}` for each article
3. Return `[{"id": N, "summary_ru": "…"}, ...]`
4. Save via `--summarize-save <file> -c <slug>` or pipe via stdin
5. Repeat for N = 0..N

Can be parallelized (up to 5 agents at once).

---

## Edge cases

- **No articles in DB** → report "Нет данных в БД." and stop
- **No new articles after update** → report "Кэш актуален: <category> — последняя статья от <DATE>" and stop
- **Corpus is metadata-only** → warn, suggest `--full-text-only`
- **All candidates in cache** → report from DB, no LLM
- **Subagent returned invalid JSON** → retry up to 2 times
- **Subagent error** → log error status, retry on next run
- **All subagents failed** → 0/5 successful → stop, notify user
- **Empty/invalid query** → report error, no stacktrace
- **Interest file with no scores** → run Orchestration Loop
- **Interrupt (Ctrl+C)** → unsaved data is lost; restart picks up where it left off
- **Network error** → inform user, suggest retry

## Notes

- CWD must be this directory for relative paths
- Tests: `pytest tests/ -v`
- Full CLI docs: `src/README.md`
- Acceptance tests: `references/ACCEPTANCE.md`
- **Do not** create temporary scripts for DB queries — use `--db-*` flags
- **Do not** ask unnecessary questions — make smart defaults

## Intent mapping (quick reference)

| User says | Action |
|-----------|--------|
| "обнови кэш", "update cache", "обнови", "refresh" | **Cache Update** | выполнить Mode 0 |
| "latest LED hacks", "последние статьи" | `--latest N -c <slug>` → summarize |
| "найди статьи про ESP32" | `--search "ESP32" -c led-hacks` |
| "какие тренды за месяц" | `--trends -c led-hacks --since <date>` |
| "еженедельная сводка" | `--digest -c led-hacks --since <date>` |
| "заскрейпь категорию" | scraper flags |
| "суммаризируй", "сделай summary" | `--summarize-status -c <slug>`, then batch summarization |
| "схема БД" | `--db-schema` |
| "статус" | `--db-summary` |
| "найди по ID [42]" | use `sqlite-query` skill → summarize |