import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from analyzer.hashes import compute_content_hash

from .schema import INDEXES_SQL, SCHEMA_SQL

logger = logging.getLogger(__name__)


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
        self._execute(
            "CREATE INDEX IF NOT EXISTS idx_articles_contenthash ON articles(content_hash)"
        )

    def _migrate(self):
        cols = [c["name"] for c in self._fetchall("PRAGMA table_info('articles')")]
        if "content_hash" not in cols:
            self._execute("ALTER TABLE articles ADD COLUMN content_hash TEXT")
        rows = self._fetchall(
            "SELECT id, title, excerpt, content_md FROM articles WHERE content_hash IS NULL"
        )
        for r in rows:
            ch = compute_content_hash(r["content_md"], r["title"] or "", r["excerpt"] or "")
            self._execute("UPDATE articles SET content_hash = ? WHERE id = ?", (ch, r["id"]))

    # ------------------------------------------------------------------
    # Scrape sessions
    # ------------------------------------------------------------------

    def create_session(self, category: str) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cur = self._execute(
            "INSERT INTO scrape_sessions (category, started_at) VALUES (?, ?)",
            (category, now),
        )
        return cur.lastrowid

    def finish_session(
        self,
        session_id: int,
        status: str = "completed",
        total_pages: Optional[int] = None,
        total_found: Optional[int] = None,
    ):
        now = datetime.now(timezone.utc).isoformat()
        fields = ["finished_at = ?", "status = ?"]
        params: list = [now, status]
        if total_pages is not None:
            fields.append("total_pages = ?")
            params.append(total_pages)
        if total_found is not None:
            fields.append("total_found = ?")
            params.append(total_found)
        params.append(session_id)
        self._execute(
            f"UPDATE scrape_sessions SET {', '.join(fields)} WHERE id = ?",
            params,
        )

    def get_last_session(self, category: str):
        return self._fetchone(
            "SELECT * FROM scrape_sessions WHERE category = ? AND status = 'completed' "
            "ORDER BY id DESC LIMIT 1",
            (category,),
        )

    def get_session_info(self, category: str):
        return self._fetchone(
            "SELECT id, started_at, finished_at, status, total_pages, total_found "
            "FROM scrape_sessions WHERE category = ? ORDER BY id DESC LIMIT 1",
            (category,),
        )

    def reset_category(self, category: str):
        self._execute("DELETE FROM comments WHERE article_url IN (SELECT url FROM articles WHERE category = ?)", (category,))
        self._execute("DELETE FROM articles WHERE category = ?", (category,))
        self._execute("DELETE FROM pages WHERE category = ?", (category,))

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------

    def mark_page_done(self, category: str, page_number: int, session_id: int, article_count: int):
        now = datetime.now(timezone.utc).isoformat()
        self._execute(
            "INSERT OR REPLACE INTO pages (category, page_number, session_id, scraped_at, status, article_count) "
            "VALUES (?, ?, ?, ?, 'done', ?)",
            (category, page_number, session_id, now, article_count),
        )

    def mark_page_error(self, category: str, page_number: int, session_id: int, error_message: str):
        now = datetime.now(timezone.utc).isoformat()
        existing = self._fetchone(
            "SELECT retry_count FROM pages WHERE category = ? AND page_number = ?",
            (category, page_number),
        )
        retry = (existing["retry_count"] + 1) if existing else 1
        self._execute(
            "INSERT OR REPLACE INTO pages (category, page_number, session_id, scraped_at, status, retry_count, error_message) "
            "VALUES (?, ?, ?, ?, 'error', ?, ?)",
            (category, page_number, session_id, now, retry, error_message),
        )

    def get_done_pages(self, category: str):
        rows = self._fetchall(
            "SELECT page_number FROM pages WHERE category = ? AND status = 'done' ORDER BY page_number",
            (category,),
        )
        return {r["page_number"] for r in rows}

    def get_error_pages(self, category: str, max_retries: int = 3):
        rows = self._fetchall(
            "SELECT page_number, retry_count FROM pages WHERE category = ? AND status = 'error' AND retry_count < ?",
            (category, max_retries),
        )
        return {r["page_number"] for r in rows}

    # ------------------------------------------------------------------
    # Articles
    # ------------------------------------------------------------------

    def upsert_article(
        self,
        category: str,
        title: str,
        url: str,
        session_id: int,
        loaded_at: str,
        date: str = "",
        excerpt: str = "",
        tags: Optional[list] = None,
        author: Optional[str] = None,
    ):
        tags_json = json.dumps(tags or [], ensure_ascii=False)
        content_hash = compute_content_hash(None, title or "", excerpt or "")
        self._execute(
            "INSERT OR IGNORE INTO articles "
            "(category, title, url, date, excerpt, tags, content_hash, session_id, loaded_at, author, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'metadata')",
            (category, title, url, date, excerpt, tags_json, content_hash, session_id, loaded_at, author),
        )

    def get_articles_for_full_text(self, category: str, since: Optional[str] = None):
        query = "SELECT id, url, date FROM articles WHERE category = ? AND (status = 'metadata' OR content_md IS NULL)"
        params = [category]
        if since:
            query += " AND date >= ?"
            params.append(since)
        return self._fetchall(query, params)

    def update_article_full_text(
        self,
        article_id: int,
        content_raw: str,
        content_md: str,
        session_id: int,
        author: Optional[str] = None,
    ):
        now = datetime.now(timezone.utc).isoformat()
        content_hash = compute_content_hash(content_md)
        fields = [
            "content_raw = ?",
            "content_md = ?",
            "content_hash = ?",
            "article_scraped_at = ?",
            "status = 'full'",
        ]
        params: list = [content_raw, content_md, content_hash, now]
        if author:
            fields.append("author = ?")
            params.append(author)
        params.append(article_id)
        self._execute(
            f"UPDATE articles SET {', '.join(fields)} WHERE id = ?",
            params,
        )

    def mark_article_error(self, article_id: int):
        self._execute(
            "UPDATE articles SET status = 'error' WHERE id = ?",
            (article_id,),
        )

    def insert_comment(self, article_id: int, article_url: str, author: str, date: str, content_md: str):
        self._execute(
            "INSERT INTO comments (article_id, article_url, author, date, content_md) VALUES (?, ?, ?, ?, ?)",
            (article_id, article_url, author, date, content_md),
        )

    # ------------------------------------------------------------------
    # Query / Info
    # ------------------------------------------------------------------

    def get_category_info(self, category: str):
        return self._fetchone(
            "SELECT "
            "  COUNT(*) as total_articles, "
            "  COALESCE(SUM(CASE WHEN status = 'full' THEN 1 ELSE 0 END), 0) as full_text_count, "
            "  MIN(date) as earliest, "
            "  MAX(date) as latest "
            "FROM articles WHERE category = ?",
            (category,),
        )

    def list_latest_articles(self, category: str, limit: int = 5):
        rows = self._fetchall(
            "SELECT id, title, date, excerpt, tags, url, content_md FROM articles WHERE category = ? "
            "ORDER BY date DESC LIMIT ?",
            (category, limit),
        )
        result = []
        for r in rows:
            result.append({
                "id": r["id"],
                "title": r["title"],
                "date": r["date"],
                "excerpt": r["excerpt"],
                "tags": json.loads(r["tags"]) if r["tags"] else [],
                "url": r["url"],
                "content_md": r["content_md"],
            })
        return result

    def get_latest_date(self, category: str) -> str | None:
        row = self._fetchone(
            "SELECT MAX(date) as latest FROM articles WHERE category = ? AND status IN ('metadata', 'full')",
            (category,),
        )
        return row["latest"] if row and row["latest"] else None

    def get_categories(self):
        rows = self._fetchall(
            "SELECT category, COUNT(*) as cnt FROM articles GROUP BY category ORDER BY category"
        )
        return [{"name": r["category"], "count": r["cnt"]} for r in rows]

    def export_articles(self, category: str, since: Optional[str] = None):
        query = (
            "SELECT title, url, author, date, excerpt, content_md, tags "
            "FROM articles WHERE category = ?"
        )
        params = [category]
        if since:
            query += " AND date >= ?"
            params.append(since)
        query += " ORDER BY date DESC"
        rows = self._fetchall(query, params)
        result = []
        for r in rows:
            article = {
                "title": r["title"],
                "url": r["url"],
                "author": r["author"],
                "date": r["date"],
                "excerpt": r["excerpt"],
                "content_md": r["content_md"],
                "tags": json.loads(r["tags"]) if r["tags"] else [],
            }
            result.append(article)
        return result

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

    def search_articles(self, keyword: str, category: Optional[str] = None, limit: int = 20) -> list[dict]:
        like = f"%{keyword}%"
        query = (
            "SELECT id, title, url, author, date, excerpt, "
            "  SUBSTR(content_md, 1, 500) as content_preview, "
            "  tags, category "
            "FROM articles WHERE (title LIKE ? OR excerpt LIKE ? OR content_md LIKE ?)"
        )
        params = [like, like, like]
        if category:
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY date DESC LIMIT ?"
        params.append(limit)
        rows = self._fetchall(query, params)
        result = []
        for r in rows:
            result.append({
                "id": r["id"],
                "title": r["title"],
                "url": r["url"],
                "author": r["author"],
                "date": r["date"],
                "excerpt": r["excerpt"],
                "content_preview": r["content_preview"],
                "tags": json.loads(r["tags"]) if r["tags"] else [],
                "category": r["category"],
            })
        return result

    def query(self, sql: str, params=None) -> list[dict]:
        upper = sql.strip().upper()
        if not upper.startswith("SELECT"):
            raise ValueError("Only SELECT queries are allowed")
        rows = self._fetchall(sql, params or ())
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Analysis scoring
    # ------------------------------------------------------------------

    def get_analysis_candidates(
        self,
        category: str,
        query_hash: str,
        rubric_hash: str,
        stage: str,
        max_retries: int = 3,
    ) -> list[dict]:
        if stage == "filter":
            rows = self._fetchall(
                """
                SELECT a.id, a.title, a.excerpt, a.tags, a.date, a.url,
                       a.content_md, a.content_hash, a.status as article_status
                FROM articles a
                WHERE a.category = ?
                  AND (
                    NOT EXISTS (
                        SELECT 1 FROM analysis_scores s
                        WHERE s.article_id = a.id
                          AND s.query_hash = ?
                          AND s.rubric_hash = ?
                          AND s.content_hash = a.content_hash
                    )
                    OR EXISTS (
                        SELECT 1 FROM analysis_scores s
                        WHERE s.article_id = a.id
                          AND s.query_hash = ?
                          AND s.rubric_hash = ?
                          AND s.content_hash = a.content_hash
                          AND s.status = 'error'
                          AND s.passed_filter IS NULL
                          AND s.attempts < ?
                    )
                  )
                ORDER BY a.date DESC
                """,
                (category, query_hash, rubric_hash, query_hash, rubric_hash, max_retries),
            )
            result = []
            for r in rows:
                tags = json.loads(r["tags"]) if r["tags"] else []
                content_md = r["content_md"] or ""
                result.append({
                    "id": r["id"],
                    "title": r["title"],
                    "excerpt": r["excerpt"] or "",
                    "tags": tags,
                    "date": r["date"],
                    "url": r["url"],
                    "content_hash": r["content_hash"],
                    "has_full_text": bool(content_md),
                })
            return result

        elif stage == "rerank":
            rows = self._fetchall(
                """
                SELECT a.id, a.title, a.excerpt, a.tags, a.date, a.url,
                       a.content_md, a.author,
                       s.content_hash, s.filter_reason
                FROM analysis_scores s
                JOIN articles a ON a.id = s.article_id
                WHERE a.category = ?
                  AND s.query_hash = ?
                  AND s.rubric_hash = ?
                  AND s.content_hash = a.content_hash
                  AND (
                    (s.status = 'kept' AND s.total IS NULL)
                    OR (s.status = 'error' AND s.attempts < ? AND s.passed_filter = 1)
                  )
                ORDER BY a.date DESC
                """,
                (category, query_hash, rubric_hash, max_retries),
            )
            result = []
            for r in rows:
                tags = json.loads(r["tags"]) if r["tags"] else []
                result.append({
                    "id": r["id"],
                    "title": r["title"],
                    "excerpt": r["excerpt"] or "",
                    "tags": tags,
                    "date": r["date"],
                    "url": r["url"],
                    "content_md": r["content_md"] or "",
                    "author": r["author"],
                    "content_hash": r["content_hash"],
                    "filter_reason": r["filter_reason"],
                })
            return result

        else:
            raise ValueError(f"Unknown stage: {stage!r}. Expected 'filter' or 'rerank'.")

    def get_analysis_comments(self, article_id: int) -> list[dict]:
        rows = self._fetchall(
            "SELECT author, date, content_md FROM comments WHERE article_id = ? ORDER BY id",
            (article_id,),
        )
        return [{"author": r["author"], "date": r["date"], "content_md": r["content_md"]} for r in rows]

    def save_analysis_filter(
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
            INSERT INTO analysis_scores
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

    def save_analysis_score(
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
            "SELECT id FROM analysis_scores "
            "WHERE article_id = ? AND query_hash = ? AND rubric_hash = ? "
            "  AND total IS NULL AND status IN ('kept', 'error') "
            "ORDER BY id DESC LIMIT 1",
            (article_id, query_hash, rubric_hash),
        )
        if not active:
            logger.warning(
                "save_analysis_score: no active row for article_id=%s (skipped)", article_id
            )
            return False
        self._execute(
            """
            UPDATE analysis_scores
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

    def mark_analysis_error(
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
            "SELECT id, attempts, passed_filter FROM analysis_scores "
            "WHERE article_id = ? AND query_hash = ? AND rubric_hash = ? AND content_hash = ?",
            (article_id, query_hash, rubric_hash, content_hash),
        )
        if existing:
            self._execute(
                "UPDATE analysis_scores SET status='error', attempts=attempts+1, last_error=? "
                "WHERE article_id=? AND query_hash=? AND rubric_hash=? AND content_hash=?",
                (error, article_id, query_hash, rubric_hash, content_hash),
            )
        else:
            self._execute(
                """
                INSERT INTO analysis_scores
                    (article_id, query_hash, query_name, query_text, rubric_hash,
                     content_hash, status, attempts, last_error)
                VALUES (?, ?, ?, ?, ?, ?, 'error', 1, ?)
                """,
                (article_id, query_hash, query_name, query_text,
                 rubric_hash, content_hash, error),
            )

    def get_analysis_report(
        self,
        category: str,
        query_hash: str,
        rubric_hash: str,
        min_total: int = 0,
        top: Optional[int] = None,
    ) -> list[dict]:
        query = (
            "SELECT a.id, a.title, a.date, a.url, a.author, a.tags, "
            "  s.scores_json, s.total, s.comment, s.filter_reason, s.status "
            "FROM analysis_scores s "
            "JOIN articles a ON a.id = s.article_id "
            "WHERE a.category = ? "
            "  AND s.query_hash = ? AND s.rubric_hash = ? "
            "  AND s.status = 'scored' AND s.total >= ? "
            "ORDER BY s.total DESC"
        )
        params: list = [category, query_hash, rubric_hash, min_total]
        if top:
            query += " LIMIT ?"
            params.append(top)
        rows = self._fetchall(query, params)
        result = []
        for r in rows:
            scores = json.loads(r["scores_json"]) if r["scores_json"] else {}
            tags = json.loads(r["tags"]) if r["tags"] else []
            result.append({
                "id": r["id"],
                "title": r["title"],
                "date": r["date"],
                "url": r["url"],
                "author": r["author"],
                "tags": tags,
                "scores": scores,
                "total": r["total"],
                "comment": r["comment"],
                "filter_reason": r["filter_reason"],
            })
        return result

    def get_analysis_status(
        self,
        category: str,
        query_hash: str,
        rubric_hash: str,
    ) -> dict:
        rows = self._fetchall(
            """
            SELECT s.status, COUNT(*) as cnt
            FROM analysis_scores s
            JOIN articles a ON a.id = s.article_id
            WHERE a.category = ? AND s.query_hash = ? AND s.rubric_hash = ?
            GROUP BY s.status
            """,
            (category, query_hash, rubric_hash),
        )
        total_articles = self._fetchone(
            "SELECT COUNT(*) as cnt FROM articles WHERE category = ?", (category,)
        )
        return {
            "total_articles": total_articles["cnt"] if total_articles else 0,
            "by_status": {r["status"]: r["cnt"] for r in rows},
        }