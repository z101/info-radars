import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from analyzer.hashes import compute_content_hash
from scraper.parser import make_month_url

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS scrape_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    status          TEXT DEFAULT 'running',
    total_months    INTEGER,
    total_found     INTEGER
);

CREATE TABLE IF NOT EXISTS scraped_months (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    year            INTEGER NOT NULL,
    month           INTEGER NOT NULL,
    session_id      INTEGER REFERENCES scrape_sessions(id),
    scraped_at      TEXT NOT NULL,
    status          TEXT DEFAULT 'done',
    article_count   INTEGER,
    consecutive_404 INTEGER DEFAULT 0,
    error_message   TEXT,
    UNIQUE(year, month)
);

CREATE TABLE IF NOT EXISTS articles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    year            INTEGER NOT NULL,
    month           INTEGER NOT NULL,
    section         TEXT,
    topic           TEXT NOT NULL,
    author          TEXT,
    page            TEXT,
    excerpt         TEXT,
    detail_url      TEXT,
    pdf_url         TEXT,
    session_id      INTEGER REFERENCES scrape_sessions(id),
    loaded_at       TEXT NOT NULL,
    format_type     TEXT,
    has_d1          INTEGER DEFAULT 0,
    UNIQUE(year, month, topic)
);

CREATE TABLE IF NOT EXISTS search_scores (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id      INTEGER NOT NULL REFERENCES articles(id),
    query_hash      TEXT NOT NULL,
    query_name      TEXT,
    query_text      TEXT,
    rubric_hash     TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    status          TEXT DEFAULT 'pending',
    passed_filter   INTEGER,
    filter_reason   TEXT,
    scores_json     TEXT,
    total           INTEGER,
    comment         TEXT,
    attempts        INTEGER DEFAULT 0,
    last_error      TEXT,
    filtered_at     TEXT,
    scored_at       TEXT,
    UNIQUE(article_id, query_hash, rubric_hash, content_hash)
);
"""

INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_articles_year_month ON articles(year, month)",
    "CREATE INDEX IF NOT EXISTS idx_articles_section ON articles(section)",
    "CREATE INDEX IF NOT EXISTS idx_articles_loaded ON articles(loaded_at)",
    "CREATE INDEX IF NOT EXISTS idx_articles_author ON articles(author)",
    "CREATE INDEX IF NOT EXISTS idx_scraped_months_year_month ON scraped_months(year, month)",
    "CREATE INDEX IF NOT EXISTS idx_scraped_months_session ON scraped_months(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_status ON scrape_sessions(status)",
    "CREATE INDEX IF NOT EXISTS idx_search_query_rubric_total ON search_scores(query_hash, rubric_hash, total)",
    "CREATE INDEX IF NOT EXISTS idx_search_query_rubric_status ON search_scores(query_hash, rubric_hash, status)",
    "CREATE INDEX IF NOT EXISTS idx_search_article ON search_scores(article_id)",
]


class Database:
    def __init__(self, db_path: str):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._local = threading.local()
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self.path), check_same_thread=False
            )
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA busy_timeout=5000")
        return self._local.conn

    def _execute(self, sql: str, params=()):
        with self._lock:
            conn = self._get_conn()
            cur = conn.execute(sql, params)
            conn.commit()
            return cur

    def _executemany(self, sql: str, params_list):
        if not params_list:
            return
        with self._lock:
            conn = self._get_conn()
            cur = conn.executemany(sql, params_list)
            conn.commit()
            return cur

    def _fetchone(self, sql: str, params=()):
        conn = self._get_conn()
        return conn.execute(sql, params).fetchone()

    def _fetchall(self, sql: str, params=()):
        conn = self._get_conn()
        return conn.execute(sql, params).fetchall()

    def _init_schema(self):
        for stmt in SCHEMA_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                self._execute(stmt)
        self._migrate()
        for idx in INDEXES_SQL:
            self._execute(idx)

    def _migrate(self):
        cols = [c["name"] for c in self._fetchall("PRAGMA table_info('articles')")]
        if "is_interesting" not in cols:
            self._execute("ALTER TABLE articles ADD COLUMN is_interesting INTEGER DEFAULT 0")
        if "is_read" not in cols:
            self._execute("ALTER TABLE articles ADD COLUMN is_read INTEGER DEFAULT 0")
        if "content_hash" not in cols:
            self._execute("ALTER TABLE articles ADD COLUMN content_hash TEXT")
            rows = self._fetchall(
                "SELECT id, topic, author, excerpt FROM articles WHERE content_hash IS NULL"
            )
            for r in rows:
                ch = compute_content_hash(r["excerpt"], r["topic"] or "", r["author"] or "")
                self._execute("UPDATE articles SET content_hash = ? WHERE id = ?", (ch, r["id"]))
        if "format_type" not in cols:
            self._execute("ALTER TABLE articles ADD COLUMN format_type TEXT")
        if "has_d1" not in cols:
            self._execute("ALTER TABLE articles ADD COLUMN has_d1 INTEGER DEFAULT 0")

    # Sessions
    def create_session(self) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cur = self._execute(
            "INSERT INTO scrape_sessions (started_at) VALUES (?)",
            (now,),
        )
        return cur.lastrowid

    def finish_session(
        self,
        session_id: int,
        status: str = "completed",
        total_months: Optional[int] = None,
        total_found: Optional[int] = None,
    ):
        now = datetime.now(timezone.utc).isoformat()
        fields = ["finished_at = ?", "status = ?"]
        params: list = [now, status]
        if total_months is not None:
            fields.append("total_months = ?")
            params.append(total_months)
        if total_found is not None:
            fields.append("total_found = ?")
            params.append(total_found)
        params.append(session_id)
        self._execute(
            f"UPDATE scrape_sessions SET {', '.join(fields)} WHERE id = ?",
            params,
        )

    def get_last_session(self):
        return self._fetchone(
            "SELECT * FROM scrape_sessions WHERE status = 'completed' "
            "ORDER BY id DESC LIMIT 1",
        )

    def get_last_scraped_month(self) -> Optional[tuple[int, int]]:
        row = self._fetchone(
            "SELECT year, month FROM scraped_months WHERE status = 'done' "
            "ORDER BY year DESC, month DESC LIMIT 1"
        )
        if row:
            return (row["year"], row["month"])
        return None

    # Scraped months
    def mark_month_done(self, year: int, month: int, session_id: int, article_count: int):
        now = datetime.now(timezone.utc).isoformat()
        self._execute(
            "INSERT OR REPLACE INTO scraped_months "
            "(year, month, session_id, scraped_at, status, article_count, consecutive_404) "
            "VALUES (?, ?, ?, ?, 'done', ?, 0)",
            (year, month, session_id, now, article_count),
        )

    def mark_month_404(self, year: int, month: int, session_id: int, consecutive_count: int):
        now = datetime.now(timezone.utc).isoformat()
        self._execute(
            "INSERT OR REPLACE INTO scraped_months "
            "(year, month, session_id, scraped_at, status, article_count, consecutive_404) "
            "VALUES (?, ?, ?, ?, '404', 0, ?)",
            (year, month, session_id, now, consecutive_count),
        )

    def mark_month_error(self, year: int, month: int, session_id: int, error: str):
        now = datetime.now(timezone.utc).isoformat()
        self._execute(
            "INSERT OR REPLACE INTO scraped_months "
            "(year, month, session_id, scraped_at, status, article_count, error_message) "
            "VALUES (?, ?, ?, ?, 'error', 0, ?)",
            (year, month, session_id, now, error),
        )

    def is_month_scraped(self, year: int, month: int) -> bool:
        row = self._fetchone(
            "SELECT id FROM scraped_months WHERE year = ? AND month = ? AND status = 'done'",
            (year, month),
        )
        return row is not None

    def get_max_consecutive_404(self) -> int:
        row = self._fetchone(
            "SELECT COALESCE(MAX(consecutive_404), 0) as max404 FROM scraped_months "
            "WHERE status = '404'"
        )
        return row["max404"] if row else 0

    # Articles
    def upsert_article(
        self,
        year: int,
        month: int,
        section: str,
        topic: str,
        author: str,
        page: str,
        detail_url: str,
        session_id: int,
        loaded_at: str,
        pdf_url: str = "",
        format_type: str = "",
        has_d1: bool = False,
    ):
        ch = compute_content_hash(None, topic or "", author or "")
        self._execute(
            "INSERT OR IGNORE INTO articles "
            "(year, month, section, topic, author, page, detail_url, pdf_url, "
            " session_id, loaded_at, content_hash, format_type, has_d1) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (year, month, section, topic, author, page, detail_url, pdf_url,
             session_id, loaded_at, ch, format_type, 1 if has_d1 else 0),
        )

    def update_article_metadata(
        self,
        year: int,
        month: int,
        section: str,
        topic: str,
        author: str,
        page: str,
        detail_url: str,
    ):
        self._execute(
            "UPDATE articles SET section=?, author=?, page=?, detail_url=? "
            "WHERE year=? AND month=? AND topic=?",
            (section, author, page, detail_url, year, month, topic),
        )

    def update_excerpt(self, topic: str, year: int, month: int, excerpt: str):
        row = self._fetchone(
            "SELECT id, topic, author FROM articles WHERE year = ? AND month = ? AND topic = ?",
            (year, month, topic),
        )
        if row:
            ch = compute_content_hash(excerpt, row["topic"] or "", row["author"] or "")
            self._execute(
                "UPDATE articles SET excerpt = ?, content_hash = ? WHERE id = ?",
                (excerpt, ch, row["id"]),
            )

    def update_pdf_url(self, topic: str, year: int, month: int, pdf_url: str):
        self._execute(
            "UPDATE articles SET pdf_url = ? WHERE year = ? AND month = ? AND topic = ?",
            (pdf_url, year, month, topic),
        )

    def upsert_articles_batch(
        self,
        articles: list[dict],
        year: int,
        month: int,
        session_id: int,
        loaded_at: str,
        fmt: str,
    ):
        if not articles:
            return
        sql = (
            "INSERT OR IGNORE INTO articles "
            "(year, month, section, topic, author, page, detail_url, pdf_url, "
            " session_id, loaded_at, content_hash, format_type, has_d1) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        params_list = []
        for art in articles:
            ch = compute_content_hash(
                None, art.get("topic", "") or "", art.get("author", "") or "",
            )
            params_list.append((
                year, month,
                art.get("section", ""),
                art.get("topic", ""),
                art.get("author", ""),
                art.get("page", ""),
                art.get("detail_url", ""),
                art.get("pdf_url", ""),
                session_id, loaded_at, ch, fmt,
                1 if art.get("has_d1") else 0,
            ))
        with self._lock:
            conn = self._get_conn()
            conn.executemany(sql, params_list)
            conn.commit()

    def update_excerpts_batch(self, items: list[tuple]) -> int:
        """
        items: list of (excerpt, topic, year, month)
        Returns count of updated rows.
        """
        if not items:
            return 0
        updated = 0
        with self._lock:
            conn = self._get_conn()
            for excerpt, topic, year, month in items:
                row = conn.execute(
                    "SELECT id, topic, author FROM articles "
                    "WHERE year = ? AND month = ? AND topic = ?",
                    (year, month, topic),
                ).fetchone()
                if row:
                    ch = compute_content_hash(
                        excerpt, row["topic"] or "", row["author"] or "",
                    )
                    conn.execute(
                        "UPDATE articles SET excerpt = ?, content_hash = ? WHERE id = ?",
                        (excerpt, ch, row["id"]),
                    )
                    updated += 1
            conn.commit()
        return updated

    def get_articles_without_excerpt(self, year: int, month: int) -> list[dict]:
        rows = self._fetchall(
            "SELECT id, topic, detail_url, year, month "
            "FROM articles WHERE year = ? AND month = ? "
            "AND (excerpt IS NULL OR excerpt = '') AND detail_url IS NOT NULL",
            (year, month),
        )
        return [dict(r) for r in rows]

    def get_articles_by_month(self, year: int, month: int) -> list[dict]:
        rows = self._fetchall(
            "SELECT id, topic, detail_url, year, month "
            "FROM articles WHERE year = ? AND month = ? AND detail_url IS NOT NULL",
            (year, month),
        )
        return [dict(r) for r in rows]

    def get_months_without_excerpts(self) -> list[dict]:
        rows = self._fetchall(
            "SELECT DISTINCT year, month FROM articles "
            "WHERE (excerpt IS NULL OR excerpt = '') AND detail_url IS NOT NULL "
            "ORDER BY year DESC, month DESC"
        )
        return [dict(r) for r in rows]

    # Info / Query
    def get_summary(self) -> dict:
        total_articles = self._fetchone("SELECT COUNT(*) as cnt FROM articles")["cnt"]
        total_months = self._fetchone(
            "SELECT COUNT(DISTINCT year || '-' || month) as cnt FROM articles"
        )["cnt"]
        date_range = self._fetchone(
            "SELECT MIN(year || '-' || SUBSTR('0' || month, -2)) as earliest, "
            "MAX(year || '-' || SUBSTR('0' || month, -2)) as latest "
            "FROM articles"
        )
        with_excerpt = self._fetchone(
            "SELECT COUNT(*) as cnt FROM articles WHERE excerpt IS NOT NULL AND excerpt != ''"
        )["cnt"]
        year_range = self._fetchone(
            "SELECT MIN(year) as min_y, MAX(year) as max_y FROM articles"
        )
        with_pdf = self._fetchone(
            "SELECT COUNT(*) as cnt FROM articles WHERE has_d1 = 1"
        )["cnt"]
        format_counts = self._fetchall(
            "SELECT format_type, COUNT(*) as cnt FROM articles "
            "WHERE format_type IS NOT NULL GROUP BY format_type"
        )
        return {
            "total_articles": total_articles,
            "total_months": total_months,
            "earliest": date_range["earliest"] if date_range else None,
            "latest": date_range["latest"] if date_range else None,
            "year_range": (year_range["min_y"], year_range["max_y"]) if year_range else None,
            "with_excerpt": with_excerpt,
            "with_pdf": with_pdf,
            "format_breakdown": {r["format_type"]: r["cnt"] for r in format_counts},
        }

    def get_latest_articles(self, limit: int = 10) -> list[dict]:
        rows = self._fetchall(
            "SELECT id, year, month, section, topic, author, page, detail_url, excerpt, "
            "is_interesting, is_read "
            "FROM articles ORDER BY year DESC, month DESC, id DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in rows]

    def get_schema(self) -> list[dict]:
        tables = self._fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        schema = []
        for t in tables:
            cols = self._fetchall(f"PRAGMA table_info('{t['name']}')")
            schema.append({
                "table": t["name"],
                "columns": [
                    {"name": c["name"], "type": c["type"], "notnull": bool(c["notnull"]), "pk": bool(c["pk"])}
                    for c in cols
                ],
            })
        return schema

    def search_articles(self, keyword: str, limit: int = 20) -> list[dict]:
        like = f"%{keyword}%"
        rows = self._fetchall(
            "SELECT id, year, month, section, topic, author, page, excerpt, detail_url "
            "FROM articles WHERE topic LIKE ? OR author LIKE ? OR section LIKE ? OR excerpt LIKE ? "
            "ORDER BY year DESC, month DESC LIMIT ?",
            (like, like, like, like, limit),
        )
        return [dict(r) for r in rows]

    def query(self, sql: str, params=None) -> list[dict]:
        upper = sql.strip().upper()
        if not upper.startswith("SELECT"):
            raise ValueError("Only SELECT queries are allowed")
        rows = self._fetchall(sql, params or ())
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Interesting / Read flags
    # ------------------------------------------------------------------
    def _update_flag(self, ids: list[int], column: str, value: int):
        if not ids:
            return
        placeholders = ",".join("?" for _ in ids)
        self._execute(
            f"UPDATE articles SET {column} = ? WHERE id IN ({placeholders})",
            [value, *ids],
        )

    def mark_interesting(self, ids: list[int]):
        self._update_flag(ids, "is_interesting", 1)

    def unmark_interesting(self, ids: list[int]):
        self._update_flag(ids, "is_interesting", 0)

    def mark_read(self, ids: list[int]):
        self._update_flag(ids, "is_read", 1)

    def unmark_read(self, ids: list[int]):
        self._update_flag(ids, "is_read", 0)

    def get_interesting_articles(self) -> list[dict]:
        rows = self._fetchall(
            "SELECT id, year, month, section, topic, author, page, excerpt, detail_url, is_read "
            "FROM articles WHERE is_interesting = 1 "
            "ORDER BY year DESC, month DESC, id DESC"
        )
        return [dict(r) for r in rows]

    def get_unread_articles(self) -> list[dict]:
        rows = self._fetchall(
            "SELECT id, year, month, section, topic, author, page, excerpt, detail_url, is_interesting "
            "FROM articles WHERE is_read = 0 "
            "ORDER BY year DESC, month DESC, id DESC"
        )
        return [dict(r) for r in rows]

    def get_articles_for_export(self, filter_mode: str = "all") -> list[dict]:
        if filter_mode == "unread":
            where = "WHERE is_read = 0"
        elif filter_mode == "interesting":
            where = "WHERE is_interesting = 1"
        else:
            where = ""
        rows = self._fetchall(
            f"SELECT id, is_interesting, is_read, year, month, section, topic, author, page, "
            f"detail_url, pdf_url, excerpt "
            f"FROM articles {where} ORDER BY year DESC, month DESC, id DESC"
        )
        result = []
        for r in rows:
            a = dict(r)
            a["month_url"] = make_month_url(a["year"], a["month"])
            a["date"] = f"{a.pop('year'):04d}-{a.pop('month'):02d}"
            a["url"] = a.pop("detail_url") or ""
            a["pdf_url"] = a.pop("pdf_url") or ""
            result.append(a)
        return result

    # ------------------------------------------------------------------
    # Search pipeline
    # ------------------------------------------------------------------
    def get_search_candidates(
        self,
        query_hash: str,
        rubric_hash: str,
        stage: str,
        max_retries: int = 3,
    ) -> list[dict]:
        if stage == "filter":
            rows = self._fetchall(
                """
                SELECT a.id, a.topic, a.author, a.section, a.page, a.year, a.month,
                       a.excerpt, a.content_hash, a.detail_url
                FROM articles a
                WHERE (
                    NOT EXISTS (
                        SELECT 1 FROM search_scores s
                        WHERE s.article_id = a.id
                          AND s.query_hash = ?
                          AND s.rubric_hash = ?
                          AND s.content_hash = a.content_hash
                    )
                    OR EXISTS (
                        SELECT 1 FROM search_scores s
                        WHERE s.article_id = a.id
                          AND s.query_hash = ?
                          AND s.rubric_hash = ?
                          AND s.content_hash = a.content_hash
                          AND s.status = 'error'
                          AND s.passed_filter IS NULL
                          AND s.attempts < ?
                    )
                )
                ORDER BY a.year DESC, a.month DESC, a.id DESC
                """,
                (query_hash, rubric_hash, query_hash, rubric_hash, max_retries),
            )
            result = []
            for r in rows:
                result.append({
                    "id": r["id"],
                    "topic": r["topic"],
                    "author": r["author"] or "",
                    "section": r["section"] or "",
                    "page": r["page"] or "",
                    "year": r["year"],
                    "month": r["month"],
                    "excerpt": r["excerpt"] or "",
                    "detail_url": r["detail_url"] or "",
                    "content_hash": r["content_hash"],
                    "has_excerpt": bool(r["excerpt"]),
                })
            return result

        elif stage == "rerank":
            rows = self._fetchall(
                """
                SELECT a.id, a.topic, a.author, a.section, a.page, a.year, a.month,
                       a.excerpt, a.detail_url,
                       s.content_hash, s.filter_reason
                FROM search_scores s
                JOIN articles a ON a.id = s.article_id
                WHERE s.query_hash = ?
                  AND s.rubric_hash = ?
                  AND s.content_hash = a.content_hash
                  AND (
                    (s.status = 'kept' AND s.total IS NULL)
                    OR (s.status = 'error' AND s.attempts < ? AND s.passed_filter = 1)
                  )
                ORDER BY a.year DESC, a.month DESC, a.id DESC
                """,
                (query_hash, rubric_hash, max_retries),
            )
            result = []
            for r in rows:
                result.append({
                    "id": r["id"],
                    "topic": r["topic"],
                    "author": r["author"] or "",
                    "section": r["section"] or "",
                    "page": r["page"] or "",
                    "year": r["year"],
                    "month": r["month"],
                    "excerpt": r["excerpt"] or "",
                    "detail_url": r["detail_url"] or "",
                    "content_hash": r["content_hash"],
                    "filter_reason": r["filter_reason"],
                })
            return result

        else:
            raise ValueError(f"Unknown stage: {stage!r}. Expected 'filter' or 'rerank'.")

    def get_search_candidates_batch(
        self,
        query_hash: str,
        rubric_hash: str,
        stage: str,
        batch: int,
        batch_size: int,
        max_retries: int = 3,
    ) -> list[dict]:
        all_candidates = self.get_search_candidates(query_hash, rubric_hash, stage, max_retries)
        start = batch * batch_size
        return all_candidates[start:start + batch_size]

    def save_search_filter(
        self,
        article_id: int,
        query_hash: str,
        query_name: str,
        query_text: str,
        rubric_hash: str,
        content_hash: str,
        keep: bool,
        reason: str,
    ):
        now = datetime.now(timezone.utc).isoformat()
        status = "kept" if keep else "dropped"
        self._execute(
            """
            INSERT INTO search_scores
                (article_id, query_hash, query_name, query_text, rubric_hash,
                 content_hash, status, passed_filter, filter_reason, filtered_at, attempts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(article_id, query_hash, rubric_hash, content_hash) DO UPDATE SET
                status        = excluded.status,
                passed_filter = excluded.passed_filter,
                filter_reason = excluded.filter_reason,
                filtered_at   = excluded.filtered_at,
                last_error    = NULL
            """,
            (article_id, query_hash, query_name, query_text, rubric_hash,
             content_hash, status, 1 if keep else 0, reason, now),
        )

    def save_search_score(
        self,
        article_id: int,
        query_hash: str,
        rubric_hash: str,
        scores: dict,
        total: int,
        comment: str,
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        scores_json = json.dumps(scores, ensure_ascii=False)
        active = self._fetchone(
            "SELECT id FROM search_scores "
            "WHERE article_id = ? AND query_hash = ? AND rubric_hash = ? "
            "  AND total IS NULL AND status IN ('kept', 'error') "
            "ORDER BY id DESC LIMIT 1",
            (article_id, query_hash, rubric_hash),
        )
        if not active:
            logger.warning(
                "save_search_score: no active row for article_id=%s (skipped)", article_id
            )
            return False
        self._execute(
            """
            UPDATE search_scores
            SET status      = 'scored',
                scores_json = ?,
                total       = ?,
                comment     = ?,
                scored_at   = ?,
                last_error  = NULL
            WHERE id = ?
            """,
            (scores_json, total, comment, now, active["id"]),
        )
        return True

    def mark_search_error(
        self,
        article_id: int,
        query_hash: str,
        rubric_hash: str,
        content_hash: str,
        stage: str,
        error: str,
        query_name: str = "",
        query_text: str = "",
    ):
        now = datetime.now(timezone.utc).isoformat()
        existing = self._fetchone(
            "SELECT id, attempts, passed_filter FROM search_scores "
            "WHERE article_id = ? AND query_hash = ? AND rubric_hash = ? AND content_hash = ?",
            (article_id, query_hash, rubric_hash, content_hash),
        )
        if existing:
            self._execute(
                "UPDATE search_scores SET status='error', attempts=attempts+1, last_error=? "
                "WHERE article_id=? AND query_hash=? AND rubric_hash=? AND content_hash=?",
                (error, article_id, query_hash, rubric_hash, content_hash),
            )
        else:
            self._execute(
                """
                INSERT INTO search_scores
                    (article_id, query_hash, query_name, query_text, rubric_hash,
                     content_hash, status, attempts, last_error)
                VALUES (?, ?, ?, ?, ?, ?, 'error', 1, ?)
                """,
                (article_id, query_hash, query_name, query_text,
                 rubric_hash, content_hash, error),
            )

    def get_search_report(
        self,
        query_hash: str,
        rubric_hash: str,
        min_total: int = 0,
        top: Optional[int] = None,
    ) -> list[dict]:
        query = (
            "SELECT a.id, a.topic, a.author, a.section, a.page, a.year, a.month, "
            "  a.detail_url, a.pdf_url, a.excerpt, a.is_interesting, a.is_read, "
            "  s.scores_json, s.total, s.comment, s.filter_reason, s.status "
            "FROM search_scores s "
            "JOIN articles a ON a.id = s.article_id "
            "WHERE s.query_hash = ? AND s.rubric_hash = ? "
            "  AND s.status = 'scored' AND s.total >= ? "
            "ORDER BY s.total DESC"
        )
        params: list = [query_hash, rubric_hash, min_total]
        if top:
            query += " LIMIT ?"
            params.append(top)
        rows = self._fetchall(query, params)
        result = []
        for r in rows:
            scores = json.loads(r["scores_json"]) if r["scores_json"] else {}
            result.append({
                "id": r["id"],
                "topic": r["topic"],
                "author": r["author"] or "",
                "section": r["section"] or "",
                "page": r["page"] or "",
                "year": r["year"],
                "month": r["month"],
                "detail_url": r["detail_url"] or "",
                "pdf_url": r["pdf_url"] or "",
                "excerpt": r["excerpt"] or "",
                "is_interesting": bool(r["is_interesting"]),
                "is_read": bool(r["is_read"]),
                "scores": scores,
                "total": r["total"],
                "comment": r["comment"] or "",
                "filter_reason": r["filter_reason"],
            })
        return result

    def get_search_status(
        self,
        query_hash: str,
        rubric_hash: str,
    ) -> dict:
        rows = self._fetchall(
            """
            SELECT s.status, COUNT(*) as cnt
            FROM search_scores s
            JOIN articles a ON a.id = s.article_id
            WHERE s.query_hash = ? AND s.rubric_hash = ?
            GROUP BY s.status
            """,
            (query_hash, rubric_hash),
        )
        total_articles = self._fetchone(
            "SELECT COUNT(*) as cnt FROM articles"
        )["cnt"]
        return {
            "total_articles": total_articles,
            "by_status": {r["status"]: r["cnt"] for r in rows},
        }