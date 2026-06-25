---
name: hackaday-blog-radar
description: >
  Fetch, scrape, and analyze articles from hackaday.com by category (LED Hacks,
  3D Printing Hacks, etc.). Use this when the user asks about Hackaday articles,
  LED projects, or wants to scrape or preview articles from hackaday.com.
---

## Role

You are a Hackaday radar operator. You control a Python scraper CLI at
`src/main.py` in this directory. Your job is to translate the user's
free-text request into the correct CLI invocation, run it, and report results.

**Always run commands from this directory** (the skill's root).

**Python runs directly** via `.venv` (repo root):
```
..\..\..\.venv\Scripts\python src\main.py <flags>
```

## Philosophy

1. **DB-first**: Always check the cache before scraping. The database is a cache
   that is easily rebuilt — use it aggressively.
2. **Autonomous**: Everything uses Python stdlib (`sqlite3` module). No external
   tools required.
3. **Efficient**: Minimise questions. Infer intent aggressively. Default to
   `led-hacks` if category is ambiguous.
4. **Safe**: Confirm before destructive actions (`--reset`).

## DB-First Workflow

### Step 0: Always start by checking the database

```powershell
..\..\..\.venv\Scripts\python src\main.py --db-summary
# or for a specific category:
..\..\..\.venv\Scripts\python src\main.py --db-summary -c <slug>
```

If the user's request can be answered from cached data — do it, explain, done.

### Step 1: Classify intent

| Intent | Examples | Action |
|--------|----------|--------|
| **DB-only** | "analyze", "report", "summary", "what's there", "find articles about X" | Query DB, no scraping |
| **Check + maybe scrape** | "latest", "new", "update", "what's new", "refresh" | Check DB date, scrape if newer articles exist |
| **Scrape** | "scrape", "download", "collect", "scrape until DATE" | Run scraper with appropriate flags |
| **Destructive** | "reset", "from scratch", "redo" | Confirm, then reset + scrape |
| **Info** | "categories", "status", "info", "how many articles" | Built-in flags only |

### Step 2: For DB-only intent — use query flags directly

```powershell
# Summary
..\..\..\.venv\Scripts\python src\main.py --db-summary -c led-hacks
..\..\..\.venv\Scripts\python src\main.py --db-summary               # all categories

# Schema
..\..\..\.venv\Scripts\python src\main.py --db-schema

# Search articles
..\..\..\.venv\Scripts\python src\main.py --db-search "ESP32" -c led-hacks

# Arbitrary SELECT query
..\..\..\.venv\Scripts\python src\main.py --db-query "SELECT title, date FROM articles WHERE category='led-hacks' LIMIT 5"
..\..\..\.venv\Scripts\python src\main.py --db-query "SELECT COUNT(*) as cnt FROM comments" --json
```

### Step 3: For scraping intent — build the command

Determine:

| Variable | How to get it |
|----------|---------------|
| **category** | Infer from keywords; default `led-hacks`. See table below. |
| **since** (incremental) | Run `--since-date -c <slug>` and use the result as `--since` |
| **until** (history cutoff) | Use if user wants articles "до января 2025", "before last year" |
| **max-pages** | Use `--max-pages N` for "N страниц" / "N страницы" (from newest) |
| **full-text** | Include `--full-text` / `-f` when user wants article content |

```powershell
# Incremental (new articles only) — requires network (-Network flag)
..\..\..\.venv\Scripts\python src\main.py -c <slug> --since 2025-01-01 --metadata-only
..\..\..\.venv\Scripts\python src\main.py -c <slug> --since 2025-01-01 -f

# Fill history (newest until cutoff)
..\..\..\.venv\Scripts\python src\main.py -c <slug> --until 2024-06-01

# Narrow window
..\..\..\.venv\Scripts\python src\main.py -c <slug> --since 2024-01-01 --until 2024-06-01

# N most recent pages
..\..\..\.venv\Scripts\python src\main.py -c <slug> --max-pages 3
```

### Step 4: Confirm destructive actions

Before running `--reset`:

1. Run `..\..\..\.venv\Scripts\python src\main.py --db-summary -c <slug>` to show current data
2. Inform the user what will be deleted
3. Ask for confirmation using the `question` tool
4. Only proceed if user explicitly confirms

### Step 5: Run the command

```powershell
..\..\..\.venv\Scripts\python src\main.py <flags>
```

Show stdout/stderr to the user in real time.

### Step 6: Post-processing

After scraping, always show final stats:

```powershell
..\..\..\.venv\Scripts\python src\main.py --db-summary -c <slug>
```

### Step 7: Show or report articles

If user asked for "latest N articles", show a quick preview:

```powershell
..\..\..\.venv\Scripts\python src\main.py --latest N -c <slug>
```

This outputs ID, title, date, URL, tags, and a short excerpt.

**To generate a formatted report with AI-summarized descriptions:**

1. Get full article data (including full text) as JSON:
   ```powershell
   ..\..\..\.venv\Scripts\python src\main.py --latest N -c <slug> --json
   ```

2. For each article, read the `content_md` field and generate a brief description (1-3 предложения на русском с интересными деталями).

3. Output the final report in this exact format:

```
[ID] Title (YYYY-MM-DD)
<URL>
Tags: <tag1, tag2>

<DESCRIPTION>

===
```

Where:
- `[ID]` — article numeric ID, e.g. `[42]`
- `<URL>` — full URL without any prefix
- `<DESCRIPTION>` — your 1-3 sentence Russian summary, generated from `content_md`
- `===` — separator between articles (with blank lines before and after)

## Intent mapping

Parse the user's free-text request into intent fields, then construct a command.

| User says (examples) | Intent | Command |
|----------------------|--------|---------|
| "latest LED hacks" / "последние LEDs" / "3 последние статьи" / "что нового по LEDs" | Show preview, then generate AI-summarized report | `--latest N -c <slug>` (preview) → `--latest N -c <slug> --json` (get full texts) → generate descriptions from `content_md` → present in `[ID]` format |
| "найди по ID [42]" / "расскажи подробнее про статью 42" | Fetch specific article by ID | `--db-query "SELECT id, title, date, url, content_md FROM articles WHERE id = 42"` → then summarize |
| "preview" / "dry run" / "посмотреть первую страницу" | Validate only, no save | `-c led-hacks --dry-run` |
| "full text" / "с содержанием" / "со статьями целиком" | Scrape with full content | `-c led-hacks --full-text` |
| "заскрейпь всё" / "full scrape" / "с нуля" | Reset + full scrape | `-c led-hacks --reset` (+ confirmation) |
| "resume" / "продолжить" | Continue interrupted scrape | `-c led-hacks` |
| "list categories" / "категории" | List categories | `--list-categories` |
| "статус" / "info" / "сколько статей" | DB info | `--db-summary -c led-hacks` |
| "export" / "экспорт" / "выгрузить" | Export to JSON | `-c led-hacks --export-json` |
| "найди статьи про ESP32" / "search for LED matrix" | Search DB | `--db-search "ESP32" -c led-hacks` |
| "до января 2025" / "until last year" / "доскрейпи до 2024" | Scrape from newest until date | `-c led-hacks --until 2025-01-01` |
| "схема БД" / "database schema" | DB schema | `--db-schema` |
| "проанализируй" / "analyze" / "отчет" | DB query | `--db-query "..."` or `--db-summary` |

**Category inference:**
- "LED", "светодиод", "LEDs" → `led-hacks`
- "3D print", "3D печать" → `3d-printing-hacks`
- "неизвестная тема" → map to closest matching category slug, or ask
- **Default**: `led-hacks` if not specified

## CLI reference (summary)

Full documentation with all flags, examples, and output formats: see `src/README.md`.

| Flag | Purpose |
|------|---------|
| `-c <slug>` | Category to scrape |
| `-f` / `--full-text` | Download full article text |
| `--since YYYY-MM-DD` | Articles newer than this date |
| `--until YYYY-MM-DD` | Scrape from newest until this cutoff |
| `--max-pages N` | Stop after N archive pages |
| `--dry-run` | Validate first page, do not save |
| `--reset` | Delete + re-scrape (confirm required) |
| `--db-schema` | Show DB schema |
| `--db-summary` | Show DB stats |
| `--db-search KEYWORD` | Search articles |
| `--db-query SQL` | Arbitrary SELECT (read-only) |
| `--json` | Output as JSON |

## Database queries (using built-in CLI flags)

Instead of learning SQL or writing Python scripts on the fly, use the built-in
query flags. All are read-only and safe.

### Get schema
```powershell
..\..\..\.venv\Scripts\python src\main.py --db-schema
..\..\..\.venv\Scripts\python src\main.py --db-schema --json
```

### Get summary
```powershell
..\..\..\.venv\Scripts\python src\main.py --db-summary
..\..\..\.venv\Scripts\python src\main.py --db-summary -c led-hacks
```

### Search articles
```powershell
..\..\..\.venv\Scripts\python src\main.py --db-search "LED matrix"
..\..\..\.venv\Scripts\python src\main.py --db-search "ESP32" -c led-hacks
```

### Arbitrary SELECT (for complex questions)
```powershell
..\..\..\.venv\Scripts\python src\main.py --db-query "SELECT title, date, url FROM articles WHERE category='led-hacks' ORDER BY date DESC LIMIT 5"
..\..\..\.venv\Scripts\python src\main.py --db-query "SELECT a.title, COUNT(c.id) as comments FROM articles a LEFT JOIN comments c ON a.id=c.article_id WHERE a.category='led-hacks' GROUP BY a.id ORDER BY comments DESC" --json
```

### Common query patterns

```sql
-- Article count per category
SELECT category, COUNT(*) as total FROM articles GROUP BY category;

-- Articles between dates
SELECT title, date, url FROM articles WHERE category='led-hacks' AND date BETWEEN '2025-01-01' AND '2025-06-01';

-- Articles with full text
SELECT title, LENGTH(content_md) as content_len FROM articles WHERE category='led-hacks' AND status='full';

-- Top authors
SELECT author, COUNT(*) as cnt FROM articles WHERE category='led-hacks' AND author IS NOT NULL GROUP BY author ORDER BY cnt DESC;

-- Tag occurrence (tags are JSON array stored as TEXT)
SELECT title, tags FROM articles WHERE category='led-hacks' AND tags LIKE '%esp32%';

-- Latest session info
SELECT * FROM scrape_sessions WHERE category='led-hacks' ORDER BY id DESC LIMIT 3;

-- Articles with comments count
SELECT a.title, COUNT(c.id) as comment_count
FROM articles a LEFT JOIN comments c ON a.id = c.article_id
WHERE a.category = 'led-hacks'
GROUP BY a.id
ORDER BY comment_count DESC;
```

## Database schema

SQLite at `data/hackaday.db` (relative path from this skill directory):
```
data/hackaday.db
```

### Tables

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `articles` | Article metadata + content | id, category, title, url, author, date, excerpt, tags (JSON), content_md, session_id, loaded_at, article_scraped_at, status ('metadata' / 'full' / 'error') |
| `comments` | Article comments | id, article_id, article_url, author, date, content_md |
| `scrape_sessions` | Scrape session tracking | id, category, started_at, finished_at, status, total_pages, total_found |
| `pages` | Per-page scrape progress | id, category, page_number, session_id, scraped_at, status, article_count, retry_count |

## Edge cases

- **No DB or empty category** → Check `--db-summary`. If empty, tell user and
  ask: "Scrape the latest page (fast, `--max-pages 1`) or full archive?"
- **DB up to date** → "Database is up to date. Last article: `<date>`."
- **Network error** → Report error, offer retry.
- **Interrupt (Ctrl+C)** → "Scrape was interrupted. Resume with `-c <slug>`."

## Notes

- CWD must be this directory for relative paths (use `cd` / `Push-Location`).
- Tests: `pytest tests/ -v`
- Full CLI docs: `src/README.md`
- **Do not** create temporary Python scripts for DB queries — use `--db-*` flags.
- **Do not** ask unnecessary questions — make smart defaults and infer intent.

---

## Analysis Orchestration

Semantic multi-agent analysis of all scraped articles driven by a free-text user query.
Оценки кэшируются в БД — повторный запуск добирает только новые/неоценённые статьи.

### Trigger

Пользователь задаёт файл запроса: **`find @../../../queries/hackaday-blog-radar/led_sculptures.md`** (или любой другой файл из корневой `queries/<skill-name>/`).
Агент читает этот файл — его текст становится `user_query`, который инжектируется в оба промпта (триаж и скоринг).

Query-файлы версионируются в git как история запросов. Файл — произвольный текст на любом языке.

### Вызов скилла для одного query (полная последовательность)

Запуск анализа по файлу `../../../queries/hackaday-blog-radar/<name>.md`. Подставь свой query-файл и категорию.
Все команды — из корня скилла, Python через .venv в корне репозитория.

```powershell
$q = "../../../queries/hackaday-blog-radar/led_sculptures.md"   # файл запроса
$c = "led-hacks"                    # категория

# 0. Состояние: что уже оценено по этому запросу
..\..\..\.venv\Scripts\python src\main.py --analysis-status -c $c --query-file $q

# 1. Кандидаты на триаж (весь корпус без строки analysis_scores)
..\..\..\.venv\Scripts\python src\main.py --analysis-candidates --stage filter -c $c --query-file $q --json

# 2. Триаж субагентами → JSON keep/drop в tmp-файл → upsert после каждого батча
..\..\..\.venv\Scripts\python src\main.py --save-analysis $tmp --stage filter -c $c --query-file $q
#   (если primary_filter.enabled=false — вместо триажа: --mark-all-kept -c $c --query-file $q)

# 3. Кандидаты на скоринг (только kept без оценок; содержат content_md + комментарии)
..\..\..\.venv\Scripts\python src\main.py --analysis-candidates --stage rerank -c $c --query-file $q --json

# 4. Скоринг субагентами → JSON scores в tmp-файл → upsert после каждого батча
..\..\..\.venv\Scripts\python src\main.py --save-analysis $tmp --stage rerank -c $c --query-file $q

# 5. Отчёт из кэша (CSV + топ в консоль)
..\..\..\.venv\Scripts\python src\main.py --analysis-report -c $c --query-file $q --top 20
```

Параметры:
- `--query-file PATH` — файл запроса (его текст → `user_query`). **Обязателен** для всех шагов анализа.
- `--top N` / `--min-total N` — ограничение отчёта (Шаг 5).

Прерванный прогон возобновляется повторным запуском тех же команд — уже обработанные статьи пропускаются (см. Cache & Resume). Подробности по каждому шагу — в разделе **Orchestration workflow** ниже.

### Architecture

```
Оркестратор (текущий агент)
  │
  ├── ..\..\..\.venv\Scripts\python src\main.py   ← .venv в корне репозитория
  │     ├── --analysis-candidates --stage filter  ← кандидаты из всего корпуса
  │     ├── --save-analysis filter.json           ← upsert результатов батча (после каждого батча)
  │     ├── --analysis-candidates --stage rerank  ← только прошедшие фильтр
  │     ├── --save-analysis rerank.json           ← upsert оценок
  │     ├── --analysis-report                     ← CSV + топ из кэша
  │     └── --analysis-status                     ← прогресс по статусам
  │
  ├── task(triage subagent 1): ~100 статей inline → JSON keep/drop
  ├── task(triage subagent 2): ~100 статей inline → JSON keep/drop
  │     ...
  ├── task(scoring subagent 1): ~20 статей inline → JSON scores
  └── task(scoring subagent 2): ~20 статей inline → JSON scores
        ...
```

### Configuration

Критерии оценки, веса и промпты заданы в `src/analyzer/config.py`.

Критерии **доменно-нейтральные** — измеряют, насколько статья подходит под `user_query`, а не задают тему. Тему несёт query-файл.

| Критерий | Вес |
|----------|-----|
| topical_relevance | 35 |
| technical_depth | 25 |
| practical_applicability | 20 |
| novelty | 10 |
| comment_signal | 10 |

`primary_filter.enabled: true`, `batch_size: 20`, `parallel_agents: 5`.

Изменение критериев/весов автоматически инвалидирует кэш (новый `rubric_hash` → cache miss).
`git add → commit` — версионирует логику.

### Orchestration workflow

#### Шаг 0. Проверить состояние

```powershell
..\..\..\.venv\Scripts\python src\main.py --db-summary -c led-hacks
..\..\..\.venv\Scripts\python src\main.py --analysis-status -c led-hacks --query-file ../../../queries/hackaday-blog-radar/led_sculptures.md
```

Если все статьи уже оценены → сразу переходить к Шагу 5 (отчёт из кэша).
Если нет статей в БД → предложить заскрейпить.

#### Шаг 1. Получить кандидатов для триажа

```powershell
..\..\..\.venv\Scripts\python src\main.py --analysis-candidates --stage filter -c led-hacks --query-file ../../../queries/hackaday-blog-radar/led_sculptures.md --json
```

Возвращает JSON-список статей без строки в `analysis_scores` для текущего запроса.
Если список пустой — все статьи уже триажированы, переходить к Шагу 3.

#### Шаг 2. Триаж (filter stage)

**Если `primary_filter.enabled: false`** — пропусти триаж субагентами и одной командой помечай всех кандидатов как kept, затем сразу к Шагу 3:

```powershell
..\..\..\.venv\Scripts\python src\main.py --mark-all-kept -c led-hacks --query-file ../../../queries/hackaday-blog-radar/led_sculptures.md
```

Иначе (фильтр включён) — прочитай `primary_filter.batch_size` из конфига (по умолчанию 100).
Раздели кандидатов на батчи. Для каждого батча:

1. Сформируй промпт из `prompt_filter` (из `analyze_config.yaml`), подставив `{user_query}` и список статей (id, title, excerpt, tags).
2. Запусти subagent параллельно через `task` tool (тип `generalPurpose` или `explore`, **без bash**).
3. Subagent возвращает строгий JSON: `[{"id": N, "keep": true, "reason": "..."}, ...]`
4. Запиши результаты батча **сразу после получения** (инкрементальная фиксация — не ждать всех батчей):

```powershell
# Запиши JSON ответа субагента во временный файл, затем:
..\..\..\.venv\Scripts\python src\main.py --save-analysis $tmpFile --stage filter -c led-hacks --query-file ../../../queries/hackaday-blog-radar/led_sculptures.md
```

**Правило recall-bias:** при сомнении субагент должен оставлять статью (`keep: true`).

**Retry:** если субагент вернул невалидный JSON → retry этот батч до 2 раз; после — строки получат `status='error'` и будут повторены при следующем прогоне.

#### Шаг 3. Получить кандидатов для скоринга

```powershell
..\..\..\.venv\Scripts\python src\main.py --analysis-candidates --stage rerank -c led-hacks --query-file ../../../queries/hackaday-blog-radar/led_sculptures.md --json
```

Возвращает только статьи со `status='kept'` без оценок. Включает `content_md` и комментарии.
Если список пустой — все прошедшие фильтр уже оценены, переходить к Шагу 5.

#### Шаг 4. Скоринг (rerank stage)

Прочитай `batch_size` (по умолчанию 20) и `parallel_agents` (по умолчанию 5).
Раздели кандидатов на батчи. Для каждого батча:

1. Сформируй промпт из `prompt_subagent`, подставив:
   - `{user_query}` — текст из query-файла
   - `{criteria_block}` — критерии с весами из `analyze_config.yaml`
   - `{articles}` — статьи **inline** (content_md + комментарии)
2. Запусти subagent через `task` tool (**без bash**, тип `generalPurpose`).
3. Subagent возвращает строгий JSON: `[{"id": N, "scores": {...}, "total": N, "comment": "..."}, ...]`
4. Запиши результаты батча **сразу**:

```powershell
..\..\..\.venv\Scripts\python src\main.py --save-analysis $tmpFile --stage rerank -c led-hacks --query-file ../../../queries/hackaday-blog-radar/led_sculptures.md
```

#### Шаг 5. Отчёт

```powershell
..\..\..\.venv\Scripts\python src\main.py --analysis-report -c led-hacks --query-file ../../../queries/hackaday-blog-radar/led_sculptures.md --top 20
```

Генерирует CSV `../../../reports/hackaday-blog-radar/<category>_analysis_<query_name>_<date>.csv` и выводит топ в консоль.
Отчёт всегда берётся из кэша БД — без LLM, быстро.

Опционально добавить `--min-total N` чтобы отсечь низкий скор.

### Cache & Resume

- Ключ кэша: `(article_id, query_hash, rubric_hash, content_hash)`. Смена query-файла или критериев → cache miss, новые строки, старые сохраняются как история.
- Новый контент после перескрейпа → новый `content_hash` → авто-инвалидация для этой статьи.
- Прерванный прогон возобновляется повторным запуском тех же команд — кандидаты выбираются по статусу, уже обработанные пропускаются.
- Ошибочные строки (`status='error'`) повторяются при следующем прогоне (до `max_retries`), затем фиксируются как постоянные ошибки и не блокируют остальное.

### Output

CSV: `../../../reports/hackaday-blog-radar/<category>_analysis_<query_name>_YYYY-MM-DD.csv`

| id | title | date | url | author | tags | topical_relevance | technical_depth | practical_applicability | novelty | comment_signal | total | comment |
|----|-------|------|-----|--------|------|-------------|--------------|----------|--------|---------------|-------|---------|

### Edge cases

- **Нет статей в БД** → сообщи пользователю, предложи заскрейпить
- **Корпус только metadata** (нет `content_md`) → предупреди, предложи дослить `--full-text-only`; скоринг пойдёт по excerpt с пониженной достоверностью
- **Все кандидаты уже в кэше** → сразу отчёт из БД, без LLM
- **Субагент вернул невалидный JSON** → retry до 2 раз; потом `status='error'`, повтор при следующем прогоне

### Subagent rules

- Тип: `generalPurpose` или `explore` (**без bash, без записи файлов**)
- Статьи передаются **inline в промпте** — субагент не читает файлы
- Субагент возвращает **строго JSON-массив**, без markdown, без пояснений
- Оркестратор записывает ответ в tmp-файл и вызывает `--save-analysis` сразу после каждого батча

### Customization

Чтобы добавить новый критерий (например, `cost_efficiency`):

1. Открой `src/analyzer/config.py`
2. Добавь в `DEFAULT_ANALYZE_CONFIG["criteria"]`:
   `cost_efficiency: { weight: 10, desc: "Доступность и дешевизна компонентов" }`
3. Уменьши веса остальных, чтобы сумма ≈ 100
4. Обнови `prompt_subagent` в том же файле (добавь критерий в описание)
5. `git add → commit` — новый `rubric_hash`, старые оценки сохраняются, новые прогоны по новой рубрике

Узкую тему (LED, 3D-печать, конкретные компоненты) задавай **в query-файле**, а не в критериях — критерии остаются общими.
