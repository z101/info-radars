import pytest
from scraper.database import Database
from analyzer.hashes import compute_query_hash, compute_rubric_hash


def _seed_article(db, sid, year=2026, month=4, topic="Test Article", author="И. Автор", excerpt=""):
    db.upsert_article(year, month, "Section", topic, author, "5", "http://d", sid, "2026-07-07T00:00:00")
    if excerpt:
        db.update_excerpt(topic, year, month, excerpt)
    return db._fetchone("SELECT id FROM articles WHERE topic = ?", (topic,))["id"]


class TestDatabase:
    def test_init_creates_tables(self, db_path):
        db = Database(db_path)
        schema = db.get_schema()
        table_names = {t["table"] for t in schema}
        assert "articles" in table_names
        assert "scrape_sessions" in table_names
        assert "scraped_months" in table_names

    def test_create_and_finish_session(self, db_path):
        db = Database(db_path)
        sid = db.create_session()
        assert sid > 0
        db.finish_session(sid, "completed", total_months=2, total_found=10)
        session = db.get_last_session()
        assert session["status"] == "completed"
        assert session["total_found"] == 10

    def test_upsert_article(self, db_path):
        db = Database(db_path)
        sid = db.create_session()
        db.upsert_article(2026, 4, "Наука и техника", "Тест статья", "И. Автор", "42", "http://detail.url", sid, "2026-07-07T00:00:00")
        articles = db.get_latest_articles(10)
        assert len(articles) == 1
        assert articles[0]["topic"] == "Тест статья"
        assert articles[0]["author"] == "И. Автор"
        assert articles[0]["page"] == "42"

    def test_upsert_deduplicates(self, db_path):
        db = Database(db_path)
        sid = db.create_session()
        db.upsert_article(2026, 4, "S1", "Same topic", "A. Author", "1", "", sid, "2026-07-07T00:00:00")
        db.upsert_article(2026, 4, "S2", "Same topic", "B. Author", "2", "", sid, "2026-07-07T00:00:00")
        articles = db.get_latest_articles(10)
        assert len(articles) == 1

    def test_mark_month_done(self, db_path):
        db = Database(db_path)
        sid = db.create_session()
        db.mark_month_done(2026, 4, sid, 5)
        assert db.is_month_scraped(2026, 4) is True
        assert db.is_month_scraped(2026, 3) is False

    def test_mark_month_404(self, db_path):
        db = Database(db_path)
        sid = db.create_session()
        db.mark_month_404(2026, 7, sid, 1)
        db.mark_month_404(2026, 6, sid, 2)
        assert db.is_month_scraped(2026, 7) is False
        max404 = db.get_max_consecutive_404()
        assert max404 >= 2

    def test_update_excerpt(self, db_path):
        db = Database(db_path)
        sid = db.create_session()
        db.upsert_article(2026, 4, "S", "Test topic", "A", "1", "http://d", sid, "2026-07-07T00:00:00")
        db.update_excerpt("Test topic", 2026, 4, "This is an excerpt")
        articles = db.get_latest_articles(10)
        assert articles[0]["excerpt"] == "This is an excerpt"

    def test_search_articles(self, db_path):
        db = Database(db_path)
        sid = db.create_session()
        db.upsert_article(2026, 4, "S", "LED Controller", "И. Иванов", "5", "", sid, "2026-07-07T00:00:00")
        db.upsert_article(2026, 3, "S", "Power Supply", "П. Петров", "10", "", sid, "2026-07-07T00:00:00")
        results = db.search_articles("LED")
        assert len(results) == 1
        assert results[0]["topic"] == "LED Controller"

    def test_get_summary(self, db_path):
        db = Database(db_path)
        sid = db.create_session()
        db.upsert_article(2026, 4, "S", "A1", "A", "1", "", sid, "2026-07-07T00:00:00")
        db.upsert_article(2026, 4, "S", "A2", "B", "2", "", sid, "2026-07-07T00:00:00")
        summary = db.get_summary()
        assert summary["total_articles"] == 2
        assert summary["total_months"] == 1
        assert summary["year_range"] == (2026, 2026)

    def test_get_schema(self, db_path):
        db = Database(db_path)
        schema = db.get_schema()
        assert len(schema) >= 3

    def test_query_only_select(self, db_path):
        db = Database(db_path)
        with pytest.raises(ValueError, match="Only SELECT"):
            db.query("DELETE FROM articles")

    def test_get_last_scraped_month(self, db_path):
        db = Database(db_path)
        sid = db.create_session()
        assert db.get_last_scraped_month() is None
        db.mark_month_done(2025, 12, sid, 3)
        db.mark_month_done(2026, 1, sid, 5)
        assert db.get_last_scraped_month() == (2026, 1)


class TestInterestingRead:
    def test_mark_interesting(self, db_path):
        db = Database(db_path)
        sid = db.create_session()
        aid = _seed_article(db, sid)
        db.mark_interesting([aid])
        arts = db.get_interesting_articles()
        assert len(arts) == 1
        assert arts[0]["id"] == aid

    def test_unmark_interesting(self, db_path):
        db = Database(db_path)
        sid = db.create_session()
        aid = _seed_article(db, sid)
        db.mark_interesting([aid])
        db.unmark_interesting([aid])
        assert db.get_interesting_articles() == []

    def test_mark_read(self, db_path):
        db = Database(db_path)
        sid = db.create_session()
        aid = _seed_article(db, sid)
        db.mark_read([aid])
        assert db.get_unread_articles() == []

    def test_unmark_read(self, db_path):
        db = Database(db_path)
        sid = db.create_session()
        aid = _seed_article(db, sid)
        db.mark_read([aid])
        db.unmark_read([aid])
        unread = db.get_unread_articles()
        assert len(unread) == 1

    def test_get_articles_for_export_all(self, db_path):
        db = Database(db_path)
        sid = db.create_session()
        _seed_article(db, sid)
        arts = db.get_articles_for_export("all")
        assert len(arts) == 1

    def test_get_articles_for_export_unread(self, db_path):
        db = Database(db_path)
        sid = db.create_session()
        aid = _seed_article(db, sid, topic="T1")
        _seed_article(db, sid, topic="T2")
        db.mark_read([aid])
        arts = db.get_articles_for_export("unread")
        assert len(arts) == 1
        assert arts[0]["topic"] == "T2"


class TestSearchPipeline:
    def test_filter_candidates_all_uncached(self, db_path):
        db = Database(db_path)
        sid = db.create_session()
        _seed_article(db, sid, topic="A1")
        _seed_article(db, sid, topic="A2")
        qh = compute_query_hash("test query")
        rh = compute_rubric_hash({"x": {"weight": 10}})
        cands = db.get_search_candidates(qh, rh, "filter")
        assert len(cands) == 2

    def test_processed_article_excluded_from_filter(self, db_path):
        db = Database(db_path)
        sid = db.create_session()
        aid = _seed_article(db, sid)
        qh = compute_query_hash("q")
        rh = compute_rubric_hash({"x": {"weight": 10}})
        cands = db.get_search_candidates(qh, rh, "filter")
        art = cands[0]
        db.save_search_filter(art["id"], qh, "q", "q", rh, art["content_hash"], True, "keep")
        remaining = db.get_search_candidates(qh, rh, "filter")
        assert len(remaining) == 0

    def test_save_filter_and_save_score(self, db_path):
        db = Database(db_path)
        sid = db.create_session()
        aid = _seed_article(db, sid)
        qh = compute_query_hash("q")
        rh = compute_rubric_hash({"x": {"weight": 10}})
        cands = db.get_search_candidates(qh, rh, "filter")
        art = cands[0]
        db.save_search_filter(art["id"], qh, "q", "q", rh, art["content_hash"], True, "ok")
        db.save_search_score(art["id"], qh, rh, {"x": 8}, 8, "good")
        report = db.get_search_report(qh, rh)
        assert len(report) == 1
        assert report[0]["total"] == 8
        assert report[0]["comment"] == "good"

    def test_candidates_batch(self, db_path):
        db = Database(db_path)
        sid = db.create_session()
        _seed_article(db, sid, topic="A1")
        _seed_article(db, sid, topic="A2")
        _seed_article(db, sid, topic="A3")
        qh = compute_query_hash("q")
        rh = compute_rubric_hash({"x": {"weight": 10}})
        batch0 = db.get_search_candidates_batch(qh, rh, "filter", 0, 2)
        assert len(batch0) == 2
        batch1 = db.get_search_candidates_batch(qh, rh, "filter", 1, 2)
        assert len(batch1) == 1

    def test_kept_articles_go_to_rerank(self, db_path):
        db = Database(db_path)
        sid = db.create_session()
        aid = _seed_article(db, sid)
        qh = compute_query_hash("q")
        rh = compute_rubric_hash({"x": {"weight": 10}})
        cands = db.get_search_candidates(qh, rh, "filter")
        art = cands[0]
        db.save_search_filter(art["id"], qh, "q", "q", rh, art["content_hash"], True, "keep")
        rerank = db.get_search_candidates(qh, rh, "rerank")
        assert len(rerank) == 1

    def test_dropped_articles_not_in_rerank(self, db_path):
        db = Database(db_path)
        sid = db.create_session()
        _seed_article(db, sid)
        qh = compute_query_hash("q")
        rh = compute_rubric_hash({"x": {"weight": 10}})
        cands = db.get_search_candidates(qh, rh, "filter")
        art = cands[0]
        db.save_search_filter(art["id"], qh, "q", "q", rh, art["content_hash"], False, "drop")
        rerank = db.get_search_candidates(qh, rh, "rerank")
        assert len(rerank) == 0

    def test_mark_search_error(self, db_path):
        db = Database(db_path)
        sid = db.create_session()
        aid = _seed_article(db, sid)
        qh = compute_query_hash("q")
        rh = compute_rubric_hash({"x": {"weight": 10}})
        cands = db.get_search_candidates(qh, rh, "filter")
        art = cands[0]
        db.mark_search_error(art["id"], qh, rh, art["content_hash"], "filter", "timeout", "q", "q")
        row = db._fetchone("SELECT status, attempts FROM search_scores WHERE article_id=?", (aid,))
        assert row["status"] == "error"
        assert row["attempts"] == 1

    def test_get_search_status(self, db_path):
        db = Database(db_path)
        sid = db.create_session()
        _seed_article(db, sid)
        qh = compute_query_hash("q")
        rh = compute_rubric_hash({"x": {"weight": 10}})
        status = db.get_search_status(qh, rh)
        assert status["total_articles"] == 1
        assert status["by_status"] == {}

    def test_migration_adds_columns(self, db_path):
        db = Database(db_path)
        cols = [c["name"] for c in db._fetchall("PRAGMA table_info('articles')")]
        assert "is_interesting" in cols
        assert "is_read" in cols
        assert "content_hash" in cols


class TestHasher:
    def test_query_hash_stable(self):
        assert compute_query_hash("test query") == compute_query_hash("test  query")

    def test_rubric_hash_stable(self):
        cfg = {"a": {"weight": 10}, "b": {"weight": 20}}
        assert compute_rubric_hash(cfg) == compute_rubric_hash({"b": {"weight": 20}, "a": {"weight": 10}})