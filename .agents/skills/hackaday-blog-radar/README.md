# hackaday-blog-radar

Семантический анализатор статей Hackaday.com: скрейпинг, семантический поиск,
обнаружение трендов и персонализированные дайджесты.

## Quick Start

```powershell
# Активировать venv (из корня репозитория)
.venv\Scripts\Activate.ps1

# Перейти в директорию скилла
cd .agents\skills\hackaday-blog-radar

# 1. Заскрейпить 1 страницу статей (быстрый старт, ~10 статей)
python src\main.py -c led-hacks --max-pages 1 --metadata-only

# 2. Семантический поиск
python src\main.py --search "LED cube with ESP32" -c led-hacks

# 3. Тренды
python src\main.py --trends -c led-hacks --since 2025-01-01
```

## Команды

### Scraping

| Флаг | Описание |
|------|----------|
| `-c, --category <slug>` | Категория (led-hacks, 3d-printing-hacks...) |
| `-f, --full-text` | Скачать полный текст статей |
| `--metadata-only` | Только метаданные, без полного текста |
| `--full-text-only` | Только докачка полного текста (без скрейпа архива) |
| `--skip-comments` | Не парсить комментарии |
| `--since YYYY-MM-DD` | Только статьи новее даты |
| `--until YYYY-MM-DD` | До даты (от новых к старым) |
| `--max-pages N` | Остановиться после N страниц архива |
| `--reset` | Удалить и перескрейпить |
| `--dry-run` | Проверить первую страницу без сохранения |

### Info

| Флаг | Описание |
|------|----------|
| `-c <slug>` | Категория (обязательно для большинства команд) |
| `--db-summary -c <slug>` | Статистика по категории |
| `--db-schema` | Схема БД |
| `--db-search <keyword>` | Поиск по ключевым словам |
| `--latest N -c <slug>` | N последних статей |
| `--since-date -c <slug>` | Дата самой свежей статьи в БД |
| `--list-categories` | Список доступных категорий |
| `--json` | Вывод в JSON (работает с `--db-summary`, `--db-schema`, `--db-search`, `--latest` и др.) |

### Search (Mode A)

| Флаг | Описание |
|------|----------|
| `--search "<text>" -c <slug>` | Ad-hoc поиск |
| `--query-file <path>` | Поиск по файлу запроса (persistent) |
| `--top N` | Ограничить вывод |
| `--min-total N` | Минимальный суммарный score |

Если статьи не оценены — Python выводит инструкцию по батчингу.
Следуй ей, затем re-run команду.

### Trend Analysis (Mode B)

| Флаг | Описание |
|------|----------|
| `--trends -c <slug> [--since D] [--until D]` | Тренды за период |
| `--trend-keyword <word>` | Фокус на ключевое слово |

Аналитика: keyword frequency, comment spikes, novel topics.

### Interest Digest (Mode C)

| Флаг | Описание |
|------|----------|
| `--digest -c <slug> [--since D] [--until D]` | Сводка по интересам |
| `--interests-dir <path>` | Папка с .md файлами интересов |

Interest-файлы: `interests/hackaday-blog-radar/<topic>.md`
Каждый файл — свободный текст на любом языке, описывающий тему.

### Анализ (продвинутый, для скриптов)

| Флаг | Описание |
|------|----------|
| `--search-candidates --stage filter\|rerank --batch N --json` | Кандидаты батчем |
| `--search-save <file> --stage filter\|rerank` | Сохранить результаты оценки |
| `--search-status -c <slug> --query-file <path>` | Статус анализа |
| `--search-report -c <slug> --query-file <path> --top N` | Отчёт из кэша |
| `--search-skip-filter -c <slug> --query-file <path>` | Пропустить триаж |

## Архитектура

```
                   main.py
                      │
        ┌─────────────┼─────────────┐
        │             │             │
   scraper/       analyzer/     database/
   fetcher        config        SQLite (WAL)
   parser         hashes
   exporter       prompts /
                  report
                  trends.py
```

### tables

- `articles` — метаданные + полный текст
- `comments` — комментарии к статьям
- `scrape_sessions` + `pages` — прогресс скрейпинга
- `search_scores` — кэш LLM-оценок `(article_id, query_hash, rubric_hash, content_hash)`
- `trend_cache` — кэш LLM-интерпретации трендов

### Pipeline

```
Scrape → Store (SQLite) → Search (triage → score → report)
                         → Trends (SQL aggregates → LLM interpretation)
                         → Digest (batch search per interest)
```

## Тестирование

```powershell
pytest tests/ -v       # 171 unit-тестов
```

Пользовательские сценарии: `ACCEPTANCE.md`

## Требования

- Python 3.10+
- Зависимости: `pip install -r requirements.txt`