import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from scraper.exporter import export_json, format_info


class TestExportJson:
    def test_export_creates_file(self, tmp_path):
        db = Mock()
        db.export_articles.return_value = [
            {"title": "A1", "url": "https://hackaday.com/1/", "author": "Auth",
             "date": "2024-01-01", "excerpt": "exc", "content_md": "**md**", "tags": ["led"]}
        ]
        result_path = export_json(db, "led-hacks", str(tmp_path))
        expected = tmp_path / "led-hacks.json"
        assert result_path == str(expected)
        assert expected.exists()
        data = json.loads(expected.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["title"] == "A1"
        assert data[0]["tags"] == ["led"]

    def test_export_empty_list(self, tmp_path):
        db = Mock()
        db.export_articles.return_value = []
        result_path = export_json(db, "empty-cat", str(tmp_path))
        expected = tmp_path / "empty-cat.json"
        assert expected.exists()
        data = json.loads(expected.read_text(encoding="utf-8"))
        assert data == []

    def test_export_with_since(self, tmp_path):
        db = Mock()
        db.export_articles.return_value = [{"title": "New"}]
        export_json(db, "test-cat", str(tmp_path), since="2024-06-01")
        db.export_articles.assert_called_once_with("test-cat", "2024-06-01")

    def test_export_creates_parent_dirs(self, tmp_path):
        db = Mock()
        db.export_articles.return_value = []
        nested = tmp_path / "nested" / "dir"
        export_json(db, "test-cat", str(nested))
        assert (nested / "test-cat.json").exists()

    def test_export_ensure_ascii_false(self, tmp_path):
        db = Mock()
        db.export_articles.return_value = [{"title": "\u0421\u0442\u0430\u0442\u044c\u044f \u043d\u0430 \u0440\u0443\u0441\u0441\u043a\u043e\u043c"}]
        export_json(db, "test-cat", str(tmp_path))
        content = (tmp_path / "test-cat.json").read_text(encoding="utf-8")
        assert "\u0421\u0442\u0430\u0442\u044c\u044f" in content


class TestFormatInfo:
    def test_with_category_and_data(self):
        db = Mock()
        db.get_category_info.return_value = {
            "total_articles": 10, "full_text_count": 5,
            "earliest": "2024-01-01", "latest": "2024-12-31",
        }
        db.get_session_info.return_value = {
            "id": 1, "started_at": "2024-06-01T12:00:00",
            "status": "completed", "total_pages": 5,
        }
        output = format_info(db, "led-hacks")
        assert "led-hacks: 10 articles (5 full text)" in output
        assert "Last scrape: 2024-06-01 12:00" in output
        assert "session #1" in output
        assert "Date range:  2024-01-01 .. 2024-12-31" in output

    def test_with_category_no_data(self):
        db = Mock()
        db.get_category_info.return_value = {"total_articles": 0, "full_text_count": 0, "earliest": None, "latest": None}
        output = format_info(db, "empty-cat")
        assert "No data for category 'empty-cat'" in output

    def test_with_category_no_session(self):
        db = Mock()
        db.get_category_info.return_value = {
            "total_articles": 5, "full_text_count": 2,
            "earliest": "2024-01-01", "latest": "2024-06-01",
        }
        db.get_session_info.return_value = None
        output = format_info(db, "led-hacks")
        assert "led-hacks: 5 articles (2 full text)" in output
        assert "Date range:  2024-01-01 .. 2024-06-01" in output

    def test_without_category_with_data(self):
        db = Mock()
        db.get_categories.return_value = [
            {"name": "led-hacks", "count": 10},
            {"name": "3d-printing-hacks", "count": 5},
        ]
        output = format_info(db)
        assert "Categories in database:" in output
        assert "led-hacks" in output
        assert "3d-printing-hacks" in output

    def test_without_category_no_data(self):
        db = Mock()
        db.get_categories.return_value = []
        output = format_info(db)
        assert "No data in database." in output


class TestFormatHelpers:
    def test_format_filter_includes_id_title(self):
        from analyzer.prompts import format_filter_articles
        articles = [{"id": 42, "title": "PWM LED", "excerpt": "abc", "tags": ["led"], "date": "2024-01-01"}]
        out = format_filter_articles(articles)
        assert "[ID 42]" in out
        assert "PWM LED" in out

    def test_format_rerank_includes_content(self):
        from analyzer.prompts import format_rerank_articles
        articles = [{
            "id": 7, "title": "Coin Cell", "excerpt": "e", "tags": [], "date": "2024-01-01",
            "content_md": "Full content here", "author": "Bob",
            "comments": [{"author": "Alice", "content_md": "Nice BC547 trick"}],
        }]
        out = format_rerank_articles(articles)
        assert "Full content here" in out
        assert "BC547" in out
        assert "Alice" in out