---
name: sqlite-query
description: >
  Queries a SQLite database by translating the user's natural-language question
  into SQL and executing it via a secure read-only executor. Use when: the user
  asks about data in a SQLite database — "сколько записей", "покажи топ-10",
  "найди статьи за март", "сколько суммаризировано", "выполни запрос к базе",
  or provides a path to a .db / .sqlite file. Triggers: .db path, "база данных",
  "бд", "sqlite", "кеш", "сколько", "покажи из базы", "запрос к базе".
invocation: auto
priority: high on SQLite queries
---

# SQLite Query Skill

You have access to a secure Python executor (`executor.py`) that only allows
read-only queries (SELECT, WITH, EXPLAIN, PRAGMA). All modifying queries are
blocked by the script.

Все запросы выполняются через `executor.py` с передачей SQL вторым аргументом:

```powershell
python .agents/skills/sqlite-query/scripts/executor.py "<db_path>" "<SQL>"
```

## Workflow

### Шаг 0: Убедиться, что venv существует

Запустить при каждом входе в скилл:

```powershell
python .agents/skills/sqlite-query/scripts/setup_venv.py
```

Если скрипт вернул `OK` — venv готов. Если ошибка — вывести пользователю
и остановиться.

**CC:** venv существует (код 0).

### Шаг 1: Получить путь к БД

Если пользователь **не указал путь**:
1. Найти `.db`, `.sqlite`, `.sqlite3` файлы в проекте (через glob,
   `Get-ChildItem -Recurse -Filter *.db` и т.п.)
2. **0 файлов** → сообщить: «В проекте не найдено SQLite-баз данных.
   Укажите путь к файлу вручную.»
3. **1 файл** → использовать без подтверждения
4. **> 1 файла** → спросить пользователя, какой открыть

Путь может быть абсолютным или относительным (от корня проекта). Если файл
не существует по указанному пути — уведомить об этом.

**CC:** Путь к БД известен, файл существует.

### Шаг 2: Исследовать схему

Всегда выполняй перед формированием SQL. Запросы выполняются через
`executor.py` с SQL вторым аргументом (путь к БД — первый):

```powershell
python .agents/skills/sqlite-query/scripts/executor.py "<db_path>" "SELECT name FROM sqlite_master WHERE type='table';"
```

Последовательно выполнить:

1. **Список таблиц:**
   ```sql
   SELECT name FROM sqlite_master WHERE type='table';
   ```

2. **DDL каждой таблицы:**
   ```sql
   SELECT sql FROM sqlite_master WHERE type='table';
   ```

3. **Колонки конкретной таблицы (для каждой таблицы):**
   ```sql
   PRAGMA table_info(<table_name>);
   ```

4. **Пример данных (3 строки) для каждой таблицы:**
   ```sql
   SELECT * FROM <table_name> LIMIT 3;
   ```

**CC:** Известны все таблицы, их колонки, типы, и образец данных.

### Шаг 3: Сформулировать SQL

На основе схемы и NL-запроса пользователя написать SQL. Проверить:
- Имена таблиц и колонок соответствуют реальным (из шага 2)
- Типы данных учтены (даты как даты, числа как числа)
- JOIN — только когда нужны данные из нескольких таблиц
- Агрегации (COUNT, SUM, AVG, GROUP BY) соответствуют вопросу

Если запрос неоднозначен — предложить 2-3 варианта и спросить пользователя.

**CC:** SQL отражает намерение пользователя, имена валидны.

### Шаг 4: Выполнить SQL

Выполни SQL напрямую через `executor.py`:

```powershell
python .agents/skills/sqlite-query/scripts/executor.py "<db_path>" "<SQL>"
```

Если результат >20 строк — показать с `LIMIT 20` и сообщить общее количество
через `SELECT COUNT(*)`. Если ошибка — исправить SQL и перезапустить.

**CC:** Результат получен (или ошибка обработана).

### Шаг 5: Интерпретировать

Дать краткое (1-3 предложения) резюме: что нашли, сколько строк, ключевые
значения, есть ли аномалии.

**CC:** Пользователь получил ответ на свой вопрос.

### Шаг 6: Уточнить

Спросить «Всё ли верно? Нужно уточнить запрос?» и при необходимости повторить
шаги 3-6.

**CC:** Пользователь подтвердил ответ или отказался от уточнений.

---

## Boundaries

- **Always do:** исследовать схему; проверять venv на старте
- **Ask first:** если найдено > 1 `.db` файла — спросить пользователя
- **Never do:** модифицировать БД (заблокировано executor.py); угадывать
  имена таблиц; выполнять SQL без исследования схемы

## Red Flags

- Агент пишет SQL **не прочитав** схему
- Агент выполняет `INSERT`/`UPDATE`/`DELETE`/`DROP` — executor.py вернёт
  ошибку, но лучше не допускать
- Агент не обрабатывает ошибку SQL («no such table») — не исправляет запрос
- Агент не показывает LIMIT при большом результате

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| «Я знаю эту БД, схему смотреть не нужно» | Имена колонок могли измениться, добавились новые таблицы. |
| «Запрос простой, можно без схемы» | Даже `SELECT *` требует знать имя таблицы. |
| «Достаточно одной таблицы» | Пользователь мог иметь в виду связанные данные. |