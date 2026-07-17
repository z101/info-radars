# Acceptance Tests — hackaday-blog-radar

Пользовательские сценарии для ручной верификации скилла.
Каждый сценарий ограничен по scope (100 статей / 1 категория / N дней).
Человек проверяет результат и принимает решение о правках.

---

## Scenario 1: Scraping — metadata

**Scope:** 1 категория, 10 страниц (~100 статей)

```powershell
python src/main.py -c led-hacks --max-pages 10 --metadata-only
```

**Проверить:**
- [ ] Количество статей ≈ 100 (10 страниц × ~10 статей)
- [ ] Заголовки не пустые, читаемые
- [ ] Даты в формате YYYY-MM-DD, в хронологическом порядке
- [ ] URL ведут на hackaday.com
- [ ] Tags — непустой JSON-массив
- [ ] `--db-summary -c led-hacks` показывает корректные цифры

**Проблемы:** если даты мигают или URL битые → проверить парсер.

---

## Scenario 2: Scraping — full-text

**Scope:** Те же 10 страниц, долить полный текст

```powershell
python src/main.py -c led-hacks --full-text-only
```

**Проверить:**
- [ ] `content_md` заполнен (не NULL, не пустой)
- [ ] Нет HTML-мусора в тексте
- [ ] Изображения не потеряны (сохранились как markdown-ссылки)
- [ ] Комментарии загружены (если есть)

**Проблемы:** HTML-мусор → проверить `_clean_content()` в main.py.

---

## Scenario 3: Scraping — resume

**Scope:** Прервать → продолжить

```powershell
python src/main.py -c led-hacks --max-pages 5 --metadata-only
# Прервать Ctrl+C после 2-3 страниц
python src/main.py -c led-hacks
```

**Проверить:**
- [ ] Нет дубликатов статей
- [ ] Пропущенные страницы докачаны
- [ ] Сессия корректно завершена (status=completed)

---

## Scenario 4: Search — basic

**Scope:** 100 статей, ad-hoc запрос

```powershell
python src/main.py --search "LED cube with ESP32" -c led-hacks --top 10
```

Если статьи не оценены — выполнить оркестрацию (см. SKILL.md).

**Проверить:**
- [ ] Топ-3 статьи действительно про LED кубы / ESP32
- [ ] Match score коррелирует с субъективной оценкой
- [ ] Evidence comment осмысленный (не пустой, не "relevant")
- [ ] Нет явных false positives в топ-10

**Критерий:** ≥8/10 в топ-10 релевантны.

**Если проблемы:**
- Много false positives → усилить `prompt_filter`
- Все scores плоские (~50/100) → tweak weights в config.py
- Evidence пустой → доработать `prompt_subagent`

---

## Scenario 5: Search — cache

**Scope:** Повтор запроса из Scenario 4

```powershell
python src/main.py --search "LED cube with ESP32" -c led-hacks --top 10
```

**Проверить:**
- [ ] Ответ мгновенный (< 1 сек)
- [ ] Результаты идентичны предыдущему запуску

---

## Scenario 6: Search — comment noise resilience

**Scope:** Статья с шумными и техническими комментариями

Шумные комментарии не отфильтровываются отдельным шагом — LLM игнорирует их при
оценке критерия `comment_signal` (см. Scoring criteria в SKILL.md).

```powershell
# Найти статью с комментариями (через sqlite-query skill)
# python .agents/skills/sqlite-query/scripts/executor.py "data/hackaday.db" "SELECT id, title FROM articles WHERE id IN (SELECT article_id FROM comments GROUP BY article_id HAVING COUNT(*) > 5) LIMIT 1"
# Создать query-файл (если нет):
# mkdir -p ../../../queries
# echo "LED projects with technical discussions" > ../../../queries/test_comments.md
# Оценить
python src/main.py --search "LED projects with technical discussions" -c led-hacks --top 10
```

**Проверить:**
- [ ] Шумные комментарии ("cool!", "+1") не влияют на score (LLM их игнорирует)
- [ ] Технические комментарии (схемы, коды) учитываются
- [ ] Отдельный `--noise-filter` шаг не требуется

---

## Scenario 7: Search — small corpus

**Scope:** 2 статьи

```powershell
# Заскрейпить 1 страницу
python src/main.py -c led-hacks --max-pages 1 --full-text
# Поиск
python src/main.py --search "LED" -c led-hacks --top 5
```

**Проверить:**
- [ ] Обработка без ошибок
- [ ] Результаты есть (даже если всего 2 статьи)
- [ ] Нет ложного ощущения "надо больше батчей"

---

## Scenario 8: Trends — keyword frequency

**Scope:** 3 месяца данных

```powershell
python src/main.py --trends -c led-hacks --since 2025-01-01 --until 2025-03-31
```

**Проверить:**
- [ ] SQL-агрегаты корректны (total articles, top authors)
- [ ] Keyword frequency имеет смысл (не пусто, не одинаково)
- [ ] Novel topics не пустой (статьи по новым темам)

---

## Scenario 9: Trends — comment spikes

**Scope:** 3 месяца данных (из Scenario 8)

**Проверить:**
- [ ] Comment spikes находят статьи с аномально высоким числом комментариев
- [ ] Аномалии действительно выходят за `avg + 2*stddev`

---

## Scenario 10: Trends — LLM interpretation

**Scope:** Результаты из Scenario 8 + 9

```powershell
# Сохранить интерпретацию
python src/main.py --save-trend-interpretation <hash> "интерпретация текстом"
# Проверить
python src/main.py --trends -c led-hacks --since 2025-01-01 --until 2025-03-31
```

**Проверить:**
- [ ] Интерпретация закэшировалась
- [ ] Повторный запуск показывает её, а не "needs_llm"

---

## Scenario 11: Digest — single interest

**Scope:** 100 статей, 1 interest-файл

```powershell
# Создать interest-файл (путь относительно корня скилла)
mkdir -p ../../../interests/hackaday-blog-radar
# Содержимое interests/hackaday-blog-radar/led-art.md:
#   Меня интересуют LED-арт-объекты и светодиодные скульптуры

# Если оценки ещё не закешированы — сначала выполнить поиск
python src/main.py --search "LED art and light sculptures" -c led-hacks --top 5

# Затем запустить дайджест
python src/main.py --digest -c led-hacks --since 2025-01-01
```

**Примечание:** Если оценки уже закешированы (от предыдущего `--search` с тем же текстом),
digest переиспользует их без повторного LLM-вызова.

**Проверить:**
- [ ] Дайджест создан в `reports/hackaday-blog-radar/digest_*.md`
- [ ] Статьи релевантны теме "LED art"
- [ ] Формат читаемый (заголовки, ссылки, описания)

---

## Scenario 12: Digest — multiple interests

**Scope:** 100 статей, 2+ interest-файла

```powershell
# interests/hackaday-blog-radar/esp32-projects.md:
# Меня интересуют проекты на ESP32
# interests/hackaday-blog-radar/3d-printed-enclosures.md:
# Меня интересуют 3D-печатные корпуса для электроники

python src/main.py --digest -c led-hacks --since 2025-01-01
```

**Проверить:**
- [ ] Каждый interest имеет свой файл дайджеста
- [ ] Сводки не смешаны
- [ ] Статьи не дублируются между файлами (без необходимости)
- [ ] Если оценки для какого-то interest уже были в кэше — они переиспользованы, нового LLM-вызова нет

---

## Scenario 15: Edge — пустая БД

```powershell
# Новая БД
python src/main.py --search "LED" -c led-hacks --db empty_test.db
```

**Проверить:**
- [ ] Сообщение: "No articles in DB"
- [ ] Нет stack trace / crash

---

## Scenario 16: Edge — невалидный запрос

```powershell
python src/main.py --search "" -c led-hacks
```

**Проверить:**
- [ ] Ошибка: "requires non-empty text"
- [ ] Возврат 1 (не 0)
- [ ] Нет stack trace