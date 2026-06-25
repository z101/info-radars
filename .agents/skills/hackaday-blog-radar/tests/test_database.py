import json
import sqlite3

import pytest

from database import Database


@pytest.fixture
def db():
    return Database(":memory:")


def _seed_article(db, url="https://hackaday.com/a/", content="content v1"):
    from datetime import datetime, timezone
    sid = db.create_session("led-hacks")
    now = datetime.now(timezone.utc).isoformat()
    db.upsert_article("led-hacks", "Art", url, sid, now, "2024-01-01", "exc", ["led"])
    row = db._fetchone("SELECT id FROM articles WHERE url=?", (url,))
    aid = row["id"]
    db.update_article_full_text(aid, "<raw>", content, sid)
    return aid, sid


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

class TestDatabaseInit:
    def test_creates_db_file(self, tmp_path):
        db_path = tmp_path / "test.db"
        Database(str(db_path))
        assert db_path.exists()

    def test_creates_all_tables(self, tmp_path):
        Database(str(tmp_path / "test.db"))
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "scrape_sessions" in tables
        assert "pages" in tables
        assert "articles" in tables
        assert "comments" in tables
        assert "analysis_scores" in tables

    def test_creates_indexes(self, tmp_path):
        Database(str(tmp_path / "test.db"))
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert "idx_articles_category" in indexes
        assert "idx_articles_date" in indexes
        assert "idx_comments_article" in indexes

    def test_creates_parent_directories(self, tmp_path):
        db_path = tmp_path / "nested" / "dir" / "test.db"
        Database(str(db_path))
        assert db_path.exists()

    def test_executemany_empty_list(self, db):
        db._executemany("INSERT INTO articles (category) VALUES (?)", [])


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

class TestDatabaseSessions:
    def test_create_session_returns_id(self, db):
        sid = db.create_session("test-cat")
        assert sid == 1
        sid2 = db.create_session("test-cat")
        assert sid2 == 2

    def test_finish_session_defaults(self, db):
        sid = db.create_session("test-cat")
        db.finish_session(sid)
        row = db._fetchone("SELECT * FROM scrape_sessions WHERE id = ?", (sid,))
        assert row["status"] == "completed"
        assert row["finished_at"] is not None
        assert row["total_pages"] is None
        assert row["total_found"] is None

    def test_finish_session_with_counts(self, db):
        sid = db.create_session("test-cat")
        db.finish_session(sid, status="failed", total_pages=10, total_found=50)
        row = db._fetchone("SELECT * FROM scrape_sessions WHERE id = ?", (sid,))
        assert row["status"] == "failed"
        assert row["total_pages"] == 10
        assert row["total_found"] == 50

    def test_get_last_session_no_sessions(self, db):
        assert db.get_last_session("test-cat") is None

    def test_get_last_session_returns_latest_completed(self, db):
        db.create_session("test-cat")
        sid2 = db.create_session("test-cat")
        db.finish_session(sid2)
        sid3 = db.create_session("test-cat")
        db.finish_session(sid3)
        last = db.get_last_session("test-cat")
        assert last["id"] == sid3

    def test_get_last_session_ignores_non_completed(self, db):
        sid = db.create_session("test-cat")
        db.finish_session(sid, status="failed")
        assert db.get_last_session("test-cat") is None

    def test_get_session_info_no_sessions(self, db):
        assert db.get_session_info("test-cat") is None

    def test_get_session_info(self, db):
        sid = db.create_session("test-cat")
        db.finish_session(sid, total_pages=5, total_found=100)
        info = db.get_session_info("test-cat")
        assert info["id"] == sid
        assert info["status"] == "completed"
        assert info["total_pages"] == 5
        assert info["total_found"] == 100


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

class TestDatabasePages:
    def test_mark_page_done(self, db):
        db.mark_page_done("test-cat", 1, 1, 10)
        row = db._fetchone("SELECT * FROM pages WHERE category = ? AND page_number = ?", ("test-cat", 1))
        assert row["status"] == "done"
        assert row["article_count"] == 10

    def test_mark_page_done_replace(self, db):
        db.mark_page_done("test-cat", 1, 1, 5)
        db.mark_page_done("test-cat", 1, 2, 8)
        rows = db._fetchall("SELECT * FROM pages WHERE category = ? AND page_number = ?", ("test-cat", 1))
        assert len(rows) == 1
        assert rows[0]["article_count"] == 8

    def test_mark_page_error_sets_retry_count(self, db):
        db.mark_page_error("test-cat", 1, 1, "timeout")
        row = db._fetchone("SELECT * FROM pages WHERE category = ? AND page_number = ?", ("test-cat", 1))
        assert row["status"] == "error"
        assert row["retry_count"] == 1
        assert row["error_message"] == "timeout"

    def test_mark_page_error_increments_retry(self, db):
        db.mark_page_error("test-cat", 1, 1, "first error")
        db.mark_page_error("test-cat", 1, 2, "second error")
        row = db._fetchone("SELECT * FROM pages WHERE category = ? AND page_number = ?", ("test-cat", 1))
        assert row["retry_count"] == 2
        assert row["session_id"] == 2

    def test_get_done_pages(self, db):
        db.mark_page_done("test-cat", 1, 1, 5)
        db.mark_page_done("test-cat", 3, 1, 3)
        assert db.get_done_pages("test-cat") == {1, 3}

    def test_get_done_pages_empty(self, db):
        assert db.get_done_pages("test-cat") == set()

    def test_get_error_pages_empty(self, db):
        assert db.get_error_pages("test-cat") == set()

    def test_get_error_pages_below_max_retries(self, db):
        db.mark_page_error("test-cat", 1, 1, "err")
        db.mark_page_error("test-cat", 2, 1, "err")
        db.mark_page_error("test-cat", 2, 2, "err")
        assert db.get_error_pages("test-cat", max_retries=3) == {1, 2}

    def test_get_error_pages_excludes_maxed_retries(self, db):
        db.mark_page_error("test-cat", 1, 1, "err")
        db.mark_page_error("test-cat", 1, 2, "err")
        db.mark_page_error("test-cat", 1, 3, "err")
        assert db.get_error_pages("test-cat", max_retries=2) == set()


# ---------------------------------------------------------------------------
# Articles
# ---------------------------------------------------------------------------

class TestDatabaseArticles:
    def test_upsert_article(self, db):
        db.upsert_article("test-cat", "Title", "https://hackaday.com/a/", 1, "2024-01-01T00:00:00")
        row = db._fetchone("SELECT * FROM articles")
        assert row["title"] == "Title"
        assert row["url"] == "https://hackaday.com/a/"
        assert row["status"] == "metadata"

    def test_upsert_article_with_tags(self, db):
        db.upsert_article("test-cat", "Title", "https://hackaday.com/a/", 1, "2024-01-01T00:00:00",
                          date="Jan 1, 2024", excerpt="excerpt", tags=["led", "arduino"])
        row = db._fetchone("SELECT * FROM articles")
        assert json.loads(row["tags"]) == ["led", "arduino"]
        assert row["date"] == "Jan 1, 2024"
        assert row["excerpt"] == "excerpt"

    def test_upsert_article_duplicate_url_ignored(self, db):
        db.upsert_article("test-cat", "Original", "https://hackaday.com/a/", 1, "2024-01-01T00:00:00")
        db.upsert_article("test-cat", "Duplicate", "https://hackaday.com/a/", 2, "2024-02-01T00:00:00")
        rows = db._fetchall("SELECT * FROM articles")
        assert len(rows) == 1
        assert rows[0]["title"] == "Original"

    def test_upsert_article_without_tags_defaults_empty(self, db):
        db.upsert_article("test-cat", "Title", "https://hackaday.com/a/", 1, "2024-01-01T00:00:00")
        row = db._fetchone("SELECT * FROM articles")
        assert json.loads(row["tags"]) == []

    def test_get_articles_for_full_text(self, db):
        db.upsert_article("test-cat", "A1", "https://hackaday.com/1/", 1, "2024-01-01T00:00:00")
        db.upsert_article("test-cat", "A2", "https://hackaday.com/2/", 1, "2024-01-02T00:00:00")
        articles = db.get_articles_for_full_text("test-cat")
        assert len(articles) == 2

    def test_get_articles_for_full_text_excludes_full(self, db):
        db.upsert_article("test-cat", "A1", "https://hackaday.com/1/", 1, "2024-01-01T00:00:00")
        row = db._fetchone("SELECT id FROM articles")
        db.update_article_full_text(row["id"], "<raw>", "**md**", 1)
        articles = db.get_articles_for_full_text("test-cat")
        assert len(articles) == 0

    def test_get_articles_for_full_text_with_since(self, db):
        db.upsert_article("test-cat", "Old", "https://hackaday.com/old/", 1, "2024-01-01T00:00:00",
                          date="2023-12-01")
        db.upsert_article("test-cat", "New", "https://hackaday.com/new/", 1, "2024-01-02T00:00:00",
                          date="2024-06-01")
        articles = db.get_articles_for_full_text("test-cat", since="2024-01-01")
        assert len(articles) == 1
        assert articles[0]["url"] == "https://hackaday.com/new/"

    def test_update_article_full_text(self, db):
        db.upsert_article("test-cat", "Title", "https://hackaday.com/a/", 1, "2024-01-01T00:00:00")
        row = db._fetchone("SELECT id FROM articles")
        db.update_article_full_text(row["id"], "<p>raw</p>", "**cleaned**", 1, author="Test Author")
        updated = db._fetchone("SELECT * FROM articles WHERE id = ?", (row["id"],))
        assert updated["content_raw"] == "<p>raw</p>"
        assert updated["content_md"] == "**cleaned**"
        assert updated["author"] == "Test Author"
        assert updated["status"] == "full"
        assert updated["article_scraped_at"] is not None

    def test_update_article_full_text_without_author(self, db):
        db.upsert_article("test-cat", "Title", "https://hackaday.com/a/", 1, "2024-01-01T00:00:00")
        row = db._fetchone("SELECT id FROM articles")
        db.update_article_full_text(row["id"], "<p>raw</p>", "**cleaned**", 1)
        updated = db._fetchone("SELECT * FROM articles WHERE id = ?", (row["id"],))
        assert updated["content_raw"] == "<p>raw</p>"
        assert updated["status"] == "full"

    def test_mark_article_error(self, db):
        db.upsert_article("test-cat", "Title", "https://hackaday.com/a/", 1, "2024-01-01T00:00:00")
        row = db._fetchone("SELECT id FROM articles")
        db.mark_article_error(row["id"])
        updated = db._fetchone("SELECT * FROM articles WHERE id = ?", (row["id"],))
        assert updated["status"] == "error"

    def test_insert_comment(self, db):
        db.upsert_article("test-cat", "Title", "https://hackaday.com/a/", 1, "2024-01-01T00:00:00")
        row = db._fetchone("SELECT id FROM articles")
        db.insert_comment(row["id"], "https://hackaday.com/a/", "Commenter", "Jan 2, 2024", "Great post!")
        comments = db._fetchall("SELECT * FROM comments")
        assert len(comments) == 1
        assert comments[0]["author"] == "Commenter"
        assert comments[0]["content_md"] == "Great post!"


# ---------------------------------------------------------------------------
# Query / Info
# ---------------------------------------------------------------------------

class TestDatabaseQueries:
    def test_get_category_info_empty(self, db):
        info = db.get_category_info("nonexistent")
        assert info["total_articles"] == 0
        assert info["full_text_count"] == 0
        assert info["earliest"] is None
        assert info["latest"] is None

    def test_get_category_info_with_data(self, db):
        db.upsert_article("test-cat", "A1", "https://hackaday.com/1/", 1, "2024-01-01T00:00:00",
                          date="2024-01-01")
        db.upsert_article("test-cat", "A2", "https://hackaday.com/2/", 1, "2024-01-02T00:00:00",
                          date="2024-06-01")
        row = db._fetchone("SELECT id FROM articles WHERE title = 'A1'")
        db.update_article_full_text(row["id"], "", "", 1)
        info = db.get_category_info("test-cat")
        assert info["total_articles"] == 2
        assert info["full_text_count"] == 1
        assert info["earliest"] == "2024-01-01"
        assert info["latest"] == "2024-06-01"

    def test_get_categories_empty(self, db):
        assert db.get_categories() == []

    def test_get_categories_with_data(self, db):
        db.upsert_article("cat-a", "A1", "https://hackaday.com/a/", 1, "2024-01-01T00:00:00")
        db.upsert_article("cat-a", "A2", "https://hackaday.com/b/", 1, "2024-01-01T00:00:00")
        db.upsert_article("cat-b", "B1", "https://hackaday.com/c/", 1, "2024-01-01T00:00:00")
        cats = db.get_categories()
        assert len(cats) == 2
        assert cats[0]["name"] == "cat-a"
        assert cats[0]["count"] == 2
        assert cats[1]["name"] == "cat-b"
        assert cats[1]["count"] == 1

    def test_reset_category(self, db):
        db.upsert_article("test-cat", "A1", "https://hackaday.com/1/", 1, "2024-01-01T00:00:00")
        db.mark_page_done("test-cat", 1, 1, 1)
        db.reset_category("test-cat")
        assert db.get_category_info("test-cat")["total_articles"] == 0
        assert db.get_done_pages("test-cat") == set()

    def test_reset_category_other_categories_unaffected(self, db):
        db.upsert_article("cat-a", "A1", "https://hackaday.com/a/", 1, "2024-01-01T00:00:00")
        db.upsert_article("cat-b", "B1", "https://hackaday.com/b/", 1, "2024-01-01T00:00:00")
        db.reset_category("cat-a")
        assert db.get_category_info("cat-a")["total_articles"] == 0
        assert db.get_category_info("cat-b")["total_articles"] == 1

    def test_export_articles(self, db):
        db.upsert_article("test-cat", "A1", "https://hackaday.com/1/", 1, "2024-01-01T00:00:00",
                          date="2024-06-01", excerpt="exc", tags=["led"])
        row = db._fetchone("SELECT id FROM articles")
        db.update_article_full_text(row["id"], "<raw>", "**md**", 1, author="Auth")
        exported = db.export_articles("test-cat")
        assert len(exported) == 1
        assert exported[0]["title"] == "A1"
        assert exported[0]["author"] == "Auth"
        assert exported[0]["content_md"] == "**md**"
        assert exported[0]["tags"] == ["led"]

    def test_export_articles_with_since(self, db):
        db.upsert_article("test-cat", "Old", "https://hackaday.com/old/", 1, "2024-01-01T00:00:00",
                          date="2023-01-01")
        db.upsert_article("test-cat", "New", "https://hackaday.com/new/", 1, "2024-01-02T00:00:00",
                          date="2024-06-01")
        exported = db.export_articles("test-cat", since="2024-01-01")
        assert len(exported) == 1
        assert exported[0]["title"] == "New"

    def test_export_articles_empty(self, db):
        assert db.export_articles("nonexistent") == []


# ---------------------------------------------------------------------------
# Analysis — hashing
# ---------------------------------------------------------------------------

class TestHashing:
    def test_query_hash_stable(self):
        from analyzer.hashes import compute_query_hash
        h1 = compute_query_hash("LED sculptures with coin cell")
        h2 = compute_query_hash("LED sculptures with coin cell")
        assert h1 == h2

    def test_query_hash_whitespace_normalized(self):
        from analyzer.hashes import compute_query_hash
        h1 = compute_query_hash("LED  sculptures\nwith  coin  cell")
        h2 = compute_query_hash("LED sculptures with coin cell")
        assert h1 == h2

    def test_query_hash_sensitive_to_content(self):
        from analyzer.hashes import compute_query_hash
        h1 = compute_query_hash("LED sculptures")
        h2 = compute_query_hash("3D printing hacks")
        assert h1 != h2

    def test_rubric_hash_stable_and_order_independent(self):
        from analyzer.hashes import compute_rubric_hash
        c1 = {"a": {"weight": 10}, "b": {"weight": 20}}
        c2 = {"b": {"weight": 20}, "a": {"weight": 10}}
        assert compute_rubric_hash(c1) == compute_rubric_hash(c1)
        assert compute_rubric_hash(c1) == compute_rubric_hash(c2)

    def test_rubric_hash_sensitive_to_weight(self):
        from analyzer.hashes import compute_rubric_hash
        c1 = {"led_patterns": {"weight": 30}}
        c2 = {"led_patterns": {"weight": 25}}
        assert compute_rubric_hash(c1) != compute_rubric_hash(c2)

    def test_content_hash_uses_content_md(self):
        from analyzer.hashes import _sha256, compute_content_hash
        h = compute_content_hash("some markdown content", "title", "excerpt")
        assert h == _sha256("some markdown content")

    def test_content_hash_fallback_to_title_excerpt(self):
        from analyzer.hashes import _sha256, compute_content_hash
        h = compute_content_hash(None, "My Title", "My Excerpt")
        assert h == _sha256("My Title\nMy Excerpt")

    def test_content_hash_empty_fallback(self):
        from analyzer.hashes import _sha256, compute_content_hash
        h = compute_content_hash("", "My Title", "My Excerpt")
        assert h == _sha256("My Title\nMy Excerpt")

    def test_content_hash_sensitive_to_content(self):
        from analyzer.hashes import compute_content_hash
        h1 = compute_content_hash("content A", "t", "e")
        h2 = compute_content_hash("content B", "t", "e")
        assert h1 != h2


# ---------------------------------------------------------------------------
# Analysis — filter / rerank candidates
# ---------------------------------------------------------------------------

class TestFilterCandidates:
    def _setup(self, db):
        from datetime import datetime, timezone
        sid = db.create_session("led-hacks")
        now = datetime.now(timezone.utc).isoformat()
        db.upsert_article("led-hacks", "Art A", "https://hackaday.com/a/", sid, now, "2024-01-01", "excerpt a", [])
        db.upsert_article("led-hacks", "Art B", "https://hackaday.com/b/", sid, now, "2024-01-02", "excerpt b", [])
        return sid

    def test_all_articles_are_candidates_initially(self, tmp_db):
        from analyzer.hashes import compute_query_hash, compute_rubric_hash
        self._setup(tmp_db)
        qh = compute_query_hash("test query")
        rh = compute_rubric_hash({"c": {"weight": 10}})
        candidates = tmp_db.get_analysis_candidates("led-hacks", qh, rh, "filter")
        assert len(candidates) == 2

    def test_processed_article_excluded(self, tmp_db):
        from analyzer.hashes import compute_query_hash, compute_rubric_hash
        self._setup(tmp_db)
        qh = compute_query_hash("test query")
        rh = compute_rubric_hash({"c": {"weight": 10}})
        candidates = tmp_db.get_analysis_candidates("led-hacks", qh, rh, "filter")
        art = candidates[0]
        tmp_db.save_analysis_filter(
            art["id"], qh, "test", "test query", rh, art["content_hash"], True, "relevant"
        )
        remaining = tmp_db.get_analysis_candidates("led-hacks", qh, rh, "filter")
        assert len(remaining) == 1
        assert remaining[0]["id"] != art["id"]

    def test_error_article_requeued_and_excluded_after_max_retries(self, tmp_db):
        from analyzer.hashes import compute_query_hash, compute_rubric_hash
        self._setup(tmp_db)
        qh = compute_query_hash("test query")
        rh = compute_rubric_hash({"c": {"weight": 10}})
        candidates = tmp_db.get_analysis_candidates("led-hacks", qh, rh, "filter")
        art = candidates[0]
        ch = art["content_hash"]
        tmp_db.mark_analysis_error(art["id"], qh, rh, ch, "filter", "timeout", "test", "test query")
        remaining = tmp_db.get_analysis_candidates("led-hacks", qh, rh, "filter", max_retries=3)
        assert art["id"] in [c["id"] for c in remaining]
        for _ in range(3):
            tmp_db.mark_analysis_error(art["id"], qh, rh, ch, "filter", "timeout", "test", "test query")
        remaining = tmp_db.get_analysis_candidates("led-hacks", qh, rh, "filter", max_retries=3)
        assert art["id"] not in [c["id"] for c in remaining]


class TestRerankCandidates:
    def _seed(self, db):
        from datetime import datetime, timezone
        sid = db.create_session("led-hacks")
        now = datetime.now(timezone.utc).isoformat()
        db.upsert_article("led-hacks", "Art A", "https://hackaday.com/a/", sid, now, "2024-01-01", "exc a", [])
        db.upsert_article("led-hacks", "Art B", "https://hackaday.com/b/", sid, now, "2024-01-02", "exc b", [])
        return sid

    def test_kept_articles_are_rerank_candidates(self, tmp_db):
        from analyzer.hashes import compute_query_hash, compute_rubric_hash
        self._seed(tmp_db)
        qh = compute_query_hash("q")
        rh = compute_rubric_hash({"x": {"weight": 10}})
        filter_cands = tmp_db.get_analysis_candidates("led-hacks", qh, rh, "filter")
        for c in filter_cands:
            tmp_db.save_analysis_filter(c["id"], qh, "q", "q", rh, c["content_hash"], True, "ok")
        rerank = tmp_db.get_analysis_candidates("led-hacks", qh, rh, "rerank")
        assert len(rerank) == 2

    def test_dropped_articles_not_in_rerank(self, tmp_db):
        from analyzer.hashes import compute_query_hash, compute_rubric_hash
        self._seed(tmp_db)
        qh = compute_query_hash("q")
        rh = compute_rubric_hash({"x": {"weight": 10}})
        filter_cands = tmp_db.get_analysis_candidates("led-hacks", qh, rh, "filter")
        tmp_db.save_analysis_filter(filter_cands[0]["id"], qh, "q", "q", rh, filter_cands[0]["content_hash"], True, "keep")
        tmp_db.save_analysis_filter(filter_cands[1]["id"], qh, "q", "q", rh, filter_cands[1]["content_hash"], False, "irrelevant")
        rerank = tmp_db.get_analysis_candidates("led-hacks", qh, rh, "rerank")
        assert len(rerank) == 1
        assert rerank[0]["id"] == filter_cands[0]["id"]

    def test_scored_article_not_in_rerank(self, tmp_db):
        from analyzer.hashes import compute_query_hash, compute_rubric_hash
        self._seed(tmp_db)
        qh = compute_query_hash("q")
        rh = compute_rubric_hash({"x": {"weight": 10}})
        filter_cands = tmp_db.get_analysis_candidates("led-hacks", qh, rh, "filter")
        art = filter_cands[0]
        tmp_db.save_analysis_filter(art["id"], qh, "q", "q", rh, art["content_hash"], True, "ok")
        tmp_db.save_analysis_score(art["id"], qh, rh, {"x": 8}, 8, "good")
        rerank = tmp_db.get_analysis_candidates("led-hacks", qh, rh, "rerank")
        assert art["id"] not in [c["id"] for c in rerank]


# ---------------------------------------------------------------------------
# Analysis — save / error
# ---------------------------------------------------------------------------

class TestSaveAnalysis:
    def _seed_article(self, db):
        from datetime import datetime, timezone
        sid = db.create_session("led-hacks")
        now = datetime.now(timezone.utc).isoformat()
        db.upsert_article("led-hacks", "Art", "https://hackaday.com/art/", sid, now, "2024-01-01", "exc", [])
        row = db._fetchone("SELECT id FROM articles WHERE url = ?", ("https://hackaday.com/art/",))
        return row["id"]

    def test_save_filter_sets_kept_status(self, tmp_db):
        aid = self._seed_article(tmp_db)
        tmp_db.save_analysis_filter(aid, "qh", "n", "text", "rh", "ch", True, "relevant")
        row = tmp_db._fetchone("SELECT status, passed_filter FROM analysis_scores WHERE article_id=?", (aid,))
        assert row["status"] == "kept"
        assert row["passed_filter"] == 1

    def test_save_filter_sets_dropped_status(self, tmp_db):
        aid = self._seed_article(tmp_db)
        tmp_db.save_analysis_filter(aid, "qh", "n", "text", "rh", "ch", False, "off-topic")
        row = tmp_db._fetchone("SELECT status, passed_filter FROM analysis_scores WHERE article_id=?", (aid,))
        assert row["status"] == "dropped"
        assert row["passed_filter"] == 0

    def test_save_filter_upserts_on_conflict(self, tmp_db):
        aid = self._seed_article(tmp_db)
        tmp_db.save_analysis_filter(aid, "qh", "n", "text", "rh", "ch", False, "first")
        tmp_db.save_analysis_filter(aid, "qh", "n", "text", "rh", "ch", True, "second")
        row = tmp_db._fetchone("SELECT status, filter_reason FROM analysis_scores WHERE article_id=?", (aid,))
        assert row["status"] == "kept"
        assert row["filter_reason"] == "second"

    def test_save_score_sets_scored_status(self, tmp_db):
        aid = self._seed_article(tmp_db)
        tmp_db.save_analysis_filter(aid, "qh", "n", "text", "rh", "ch", True, "ok")
        ok = tmp_db.save_analysis_score(aid, "qh", "rh", {"x": 20}, 20, "great")
        assert ok is True
        row = tmp_db._fetchone("SELECT status, total FROM analysis_scores WHERE article_id=?", (aid,))
        assert row["status"] == "scored"
        assert row["total"] == 20

    def test_save_score_returns_false_without_active_row(self, tmp_db):
        aid = self._seed_article(tmp_db)
        ok = tmp_db.save_analysis_score(aid, "qh", "rh", {"x": 1}, 1, "c")
        assert ok is False
        row = tmp_db._fetchone("SELECT COUNT(*) AS n FROM analysis_scores WHERE article_id=?", (aid,))
        assert row["n"] == 0

    def test_save_score_updates_kept_row_after_content_drift(self, tmp_db):
        aid, sid = _seed_article(tmp_db, content="content v1")
        from analyzer.hashes import compute_query_hash, compute_rubric_hash
        qh = compute_query_hash("q")
        rh = compute_rubric_hash({"x": {"weight": 10}})
        ch_v1 = next(c["content_hash"] for c in tmp_db.get_analysis_candidates("led-hacks", qh, rh, "filter") if c["id"] == aid)
        tmp_db.save_analysis_filter(aid, qh, "n", "q", rh, ch_v1, True, "ok")
        tmp_db.update_article_full_text(aid, "<raw>", "content v2 drift", sid)
        ok = tmp_db.save_analysis_score(aid, qh, rh, {"x": 5}, 5, "c")
        assert ok is True


class TestErrorTracking:
    def _seed_article(self, db):
        from datetime import datetime, timezone
        sid = db.create_session("led-hacks")
        now = datetime.now(timezone.utc).isoformat()
        db.upsert_article("led-hacks", "Art", "https://hackaday.com/a/", sid, now, "2024-01-01", "e", [])
        row = db._fetchone("SELECT id FROM articles WHERE url=?", ("https://hackaday.com/a/",))
        return row["id"]

    def test_mark_error_creates_row(self, tmp_db):
        aid = self._seed_article(tmp_db)
        tmp_db.mark_analysis_error(aid, "qh", "rh", "ch", "filter", "timeout", "n", "q")
        row = tmp_db._fetchone("SELECT status, attempts, last_error FROM analysis_scores WHERE article_id=?", (aid,))
        assert row["status"] == "error"
        assert row["attempts"] == 1
        assert "timeout" in row["last_error"]

    def test_mark_error_increments_attempts(self, tmp_db):
        aid = self._seed_article(tmp_db)
        tmp_db.mark_analysis_error(aid, "qh", "rh", "ch", "filter", "err1", "n", "q")
        tmp_db.mark_analysis_error(aid, "qh", "rh", "ch", "filter", "err2", "n", "q")
        row = tmp_db._fetchone("SELECT attempts FROM analysis_scores WHERE article_id=?", (aid,))
        assert row["attempts"] == 2

    def test_save_filter_after_error_clears_last_error(self, tmp_db):
        aid = self._seed_article(tmp_db)
        tmp_db.mark_analysis_error(aid, "qh", "rh", "ch", "filter", "boom", "n", "q")
        tmp_db.save_analysis_filter(aid, "qh", "n", "q", "rh", "ch", True, "ok")
        row = tmp_db._fetchone("SELECT last_error FROM analysis_scores WHERE article_id=?", (aid,))
        assert row["last_error"] is None


# ---------------------------------------------------------------------------
# Analysis — report / status
# ---------------------------------------------------------------------------

class TestAnalysisReport:
    def _seed_scored(self, db):
        from datetime import datetime, timezone
        sid = db.create_session("led-hacks")
        now = datetime.now(timezone.utc).isoformat()
        qh, rh = "qh_report", "rh_report"
        scores = [80, 50, 30, 10]
        for i, total in enumerate(scores):
            url = f"https://hackaday.com/art{i}/"
            db.upsert_article("led-hacks", f"Art {i}", url, sid, now, f"2024-0{i+1}-01", "exc", [])
            row = db._fetchone("SELECT id FROM articles WHERE url=?", (url,))
            aid = row["id"]
            db.save_analysis_filter(aid, qh, "n", "q", rh, f"ch{i}", True, "ok")
            db.save_analysis_score(aid, qh, rh, {"x": total}, total, f"comment {i}")
        return qh, rh

    def test_report_sorted_by_total_desc(self, tmp_db):
        qh, rh = self._seed_scored(tmp_db)
        report = tmp_db.get_analysis_report("led-hacks", qh, rh)
        totals = [r["total"] for r in report]
        assert totals == sorted(totals, reverse=True)

    def test_report_top_limit(self, tmp_db):
        qh, rh = self._seed_scored(tmp_db)
        report = tmp_db.get_analysis_report("led-hacks", qh, rh, top=2)
        assert len(report) == 2
        assert report[0]["total"] == 80

    def test_report_min_total_filter(self, tmp_db):
        qh, rh = self._seed_scored(tmp_db)
        report = tmp_db.get_analysis_report("led-hacks", qh, rh, min_total=40)
        assert all(r["total"] >= 40 for r in report)

    def test_report_empty_before_scoring(self, tmp_db):
        from datetime import datetime, timezone
        sid = tmp_db.create_session("led-hacks")
        now = datetime.now(timezone.utc).isoformat()
        tmp_db.upsert_article("led-hacks", "Art", "https://hackaday.com/x/", sid, now, "2024-01-01", "e", [])
        report = tmp_db.get_analysis_report("led-hacks", "qh", "rh")
        assert report == []


class TestAnalysisStatus:
    def test_status_counts(self, tmp_db):
        from datetime import datetime, timezone
        sid = tmp_db.create_session("led-hacks")
        now = datetime.now(timezone.utc).isoformat()
        qh, rh = "qh_s", "rh_s"
        for i in range(3):
            tmp_db.upsert_article("led-hacks", f"A{i}", f"https://hackaday.com/s{i}/", sid, now, "2024-01-01", "e", [])
            row = tmp_db._fetchone("SELECT id FROM articles WHERE url=?", (f"https://hackaday.com/s{i}/",))
            aid = row["id"]
            if i == 0:
                tmp_db.save_analysis_filter(aid, qh, "n", "q", rh, f"ch{i}", True, "ok")
                tmp_db.save_analysis_score(aid, qh, rh, {}, 50, "c")
            elif i == 1:
                tmp_db.save_analysis_filter(aid, qh, "n", "q", rh, f"ch{i}", False, "drop")
            else:
                tmp_db.mark_analysis_error(aid, qh, rh, f"ch{i}", "filter", "boom", "n", "q")
        status = tmp_db.get_analysis_status("led-hacks", qh, rh)
        assert status["total_articles"] == 3
        assert status["by_status"]["scored"] == 1
        assert status["by_status"]["dropped"] == 1
        assert status["by_status"]["error"] == 1


class TestContentHashInvalidation:
    def test_content_change_requeues_in_filter(self, tmp_db):
        aid, sid = _seed_article(tmp_db, content="content v1")
        from analyzer.hashes import compute_query_hash, compute_rubric_hash
        qh = compute_query_hash("q")
        rh = compute_rubric_hash({"x": {"weight": 10}})
        cands = tmp_db.get_analysis_candidates("led-hacks", qh, rh, "filter")
        assert aid in [c["id"] for c in cands]
        ch_v1 = next(c["content_hash"] for c in cands if c["id"] == aid)
        tmp_db.save_analysis_filter(aid, qh, "n", "q", rh, ch_v1, True, "ok")
        tmp_db.save_analysis_score(aid, qh, rh, {"x": 8}, 8, "good")
        assert aid not in [c["id"] for c in tmp_db.get_analysis_candidates("led-hacks", qh, rh, "filter")]
        tmp_db.update_article_full_text(aid, "<raw>", "content v2 CHANGED", sid)
        cands2 = tmp_db.get_analysis_candidates("led-hacks", qh, rh, "filter")
        assert aid in [c["id"] for c in cands2]
        ch_v2 = next(c["content_hash"] for c in cands2 if c["id"] == aid)
        assert ch_v2 != ch_v1

    def test_rerank_error_stays_in_rerank_only(self, tmp_db):
        aid, _ = _seed_article(tmp_db, content="content v1")
        from analyzer.hashes import compute_query_hash, compute_rubric_hash
        qh = compute_query_hash("q")
        rh = compute_rubric_hash({"x": {"weight": 10}})
        ch = next(c["content_hash"] for c in tmp_db.get_analysis_candidates("led-hacks", qh, rh, "filter") if c["id"] == aid)
        tmp_db.save_analysis_filter(aid, qh, "n", "q", rh, ch, True, "ok")
        tmp_db.mark_analysis_error(aid, qh, rh, ch, "rerank", "boom", "n", "q")
        assert aid not in [c["id"] for c in tmp_db.get_analysis_candidates("led-hacks", qh, rh, "filter")]
        assert aid in [c["id"] for c in tmp_db.get_analysis_candidates("led-hacks", qh, rh, "rerank")]

    def test_content_hash_consistency(self, tmp_db):
        from analyzer.hashes import compute_content_hash, compute_query_hash, compute_rubric_hash
        from datetime import datetime, timezone
        sid = tmp_db.create_session("led-hacks")
        now = datetime.now(timezone.utc).isoformat()
        title, excerpt = "Meta Only", "just an excerpt"
        url = "https://hackaday.com/meta/"
        tmp_db.upsert_article("led-hacks", title, url, sid, now, "2024-01-01", excerpt, [])
        cands = tmp_db.get_analysis_candidates("led-hacks", compute_query_hash("q"), compute_rubric_hash({"x": {"weight": 10}}), "filter")
        ch = next(c["content_hash"] for c in cands if c["url"] == url)
        assert ch == compute_content_hash(None, title, excerpt)
        aid, _ = _seed_article(tmp_db, content="full body text")
        row = tmp_db._fetchone("SELECT content_hash FROM articles WHERE id=?", (aid,))
        assert row["content_hash"] == compute_content_hash("full body text")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db():
    return Database(":memory:")