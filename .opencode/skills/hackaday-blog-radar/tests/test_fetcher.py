import time
from unittest.mock import Mock, patch

import pytest
import requests

from scraper.fetcher import (
    AdaptiveRateLimiter,
    RequestConfig,
    fetch_all_parallel,
    fetch_available_categories,
    fetch_html,
)


@pytest.fixture
def config():
    return RequestConfig()


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class TestAdaptiveRateLimiter:
    @pytest.fixture
    def fast_config(self):
        return RequestConfig(delay_min=0.01, delay_max=0.02)

    def test_initial_delay_is_min(self, config):
        rl = AdaptiveRateLimiter(config)
        assert rl._delay == config.delay_min

    def test_wait_blocks_when_called_rapidly(self, fast_config):
        rl = AdaptiveRateLimiter(fast_config)
        t0 = time.perf_counter()
        rl.wait()
        rl.wait()
        elapsed = time.perf_counter() - t0
        assert elapsed >= 0.008

    def test_consecutive_errors_tracking(self, config):
        rl = AdaptiveRateLimiter(config)
        assert rl._consecutive_errors == 0
        rl.report_error()
        assert rl._consecutive_errors == 1
        rl.report_error()
        assert rl._consecutive_errors == 2
        rl.report_success()
        assert rl._consecutive_errors == 0

    @pytest.mark.parametrize("status,should_increase", [
        (429, True), (503, True), (404, False), (None, False),
    ])
    def test_report_error_behavior(self, config, status, should_increase):
        rl = AdaptiveRateLimiter(config)
        initial = rl._delay
        rl.report_error(status_code=status)
        if should_increase:
            assert rl._delay > initial
        else:
            assert rl._delay == initial

    def test_report_success_decreases_delay(self, config):
        rl = AdaptiveRateLimiter(config)
        rl._delay = 5.0
        rl.report_success()
        assert rl._delay < 5.0

    def test_report_success_does_not_go_below_min(self, config):
        rl = AdaptiveRateLimiter(config)
        rl.report_success()
        rl.report_success()
        rl.report_success()
        assert rl._delay >= config.delay_min

    def test_report_error_does_not_exceed_max(self, config):
        rl = AdaptiveRateLimiter(config)
        rl._delay = config.delay_max * 0.9
        rl.report_error(status_code=429)
        assert rl._delay <= config.delay_max


# ---------------------------------------------------------------------------
# fetch_html
# ---------------------------------------------------------------------------

class TestFetchHTML:
    @pytest.fixture(autouse=True)
    def _no_sleep(self):
        with patch("scraper.fetcher.time.sleep"):
            yield

    @patch("scraper.fetcher.requests.get")
    def test_success(self, mock_get, config):
        mock_get.return_value = Mock(status_code=200, text="<html>ok</html>")
        mock_get.return_value.raise_for_status = Mock()
        rl = AdaptiveRateLimiter(config)
        result = fetch_html("https://hackaday.com/", config, rl)
        assert result == "<html>ok</html>"

    @patch("scraper.fetcher.requests.get")
    def test_http_error_404_no_retry(self, mock_get, config):
        resp = Mock(status_code=404)
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
        mock_get.return_value = resp
        rl = AdaptiveRateLimiter(config)
        with pytest.raises(requests.HTTPError):
            fetch_html("https://hackaday.com/", config, rl)
        assert mock_get.call_count == 1

    @patch("scraper.fetcher.requests.get")
    def test_retry_on_429_and_connection_error(self, mock_get, config):
        config.max_retries = 3
        error_resp = Mock(status_code=429)
        error_resp.raise_for_status.side_effect = requests.HTTPError(response=error_resp)
        ok_resp = Mock(status_code=200, text="<html>ok</html>")
        ok_resp.raise_for_status = Mock()
        mock_get.side_effect = [error_resp, error_resp, ok_resp]
        rl = AdaptiveRateLimiter(config)
        result = fetch_html("https://hackaday.com/", config, rl)
        assert result == "<html>ok</html>"
        assert mock_get.call_count == 3

    @patch("scraper.fetcher.requests.get")
    def test_retry_exhausted_on_429(self, mock_get, config):
        config.max_retries = 2
        error_resp = Mock(status_code=429)
        error_resp.raise_for_status.side_effect = requests.HTTPError(response=error_resp)
        mock_get.return_value = error_resp
        rl = AdaptiveRateLimiter(config)
        with pytest.raises(requests.HTTPError):
            fetch_html("https://hackaday.com/", config, rl)
        assert mock_get.call_count == 2

    @patch("scraper.fetcher.requests.get")
    def test_connection_error_retries(self, mock_get, config):
        config.max_retries = 3
        mock_get.side_effect = [
            requests.ConnectionError(),
            requests.ConnectionError(),
            Mock(status_code=200, text="<html>ok</html>"),
        ]
        mock_get.return_value.raise_for_status = Mock()
        rl = AdaptiveRateLimiter(config)
        result = fetch_html("https://hackaday.com/", config, rl)
        assert result == "<html>ok</html>"
        assert mock_get.call_count == 3

    @patch("scraper.fetcher.requests.get")
    def test_timeout_retries_then_raises(self, mock_get, config):
        config.max_retries = 2
        mock_get.side_effect = [requests.Timeout(), requests.Timeout()]
        rl = AdaptiveRateLimiter(config)
        with pytest.raises(requests.Timeout):
            fetch_html("https://hackaday.com/", config, rl)
        assert mock_get.call_count == 2


# ---------------------------------------------------------------------------
# fetch_available_categories
# ---------------------------------------------------------------------------

class TestFetchAvailableCategories:
    @patch("scraper.fetcher.requests.get")
    def test_success(self, mock_get, config):
        mock_get.return_value.json.return_value = [
            {"slug": "led-hacks", "name": "LED Hacks"},
            {"slug": "3d-printing-hacks", "name": "3D Printing Hacks"},
        ]
        mock_get.return_value.raise_for_status = Mock()
        result = fetch_available_categories(config)
        assert ("led-hacks", "LED Hacks") in result
        assert ("3d-printing-hacks", "3D Printing Hacks") in result

    @patch("scraper.fetcher.requests.get")
    def test_filters_ignored_slugs(self, mock_get, config):
        mock_get.return_value.json.return_value = [
            {"slug": "led-hacks", "name": "LED Hacks"},
            {"slug": "featured", "name": "Featured"},
            {"slug": "hackaday-prize", "name": "Prize"},
        ]
        mock_get.return_value.raise_for_status = Mock()
        result = fetch_available_categories(config)
        slugs = [s for s, _ in result]
        assert "led-hacks" in slugs
        assert "featured" not in slugs
        assert "hackaday-prize" not in slugs

    @patch("scraper.fetcher.requests.get")
    def test_empty_and_error_returns_fallback(self, mock_get, config):
        mock_get.return_value.json.return_value = []
        mock_get.return_value.raise_for_status = Mock()
        result = fetch_available_categories(config)
        assert ("led-hacks", "LED Hacks") in result
        mock_get.return_value.raise_for_status.side_effect = requests.HTTPError(response=Mock(status_code=500))
        result = fetch_available_categories(config)
        assert ("led-hacks", "LED Hacks") in result
        mock_get.side_effect = requests.ConnectionError()
        result = fetch_available_categories(config)
        assert ("led-hacks", "LED Hacks") in result

    @patch("scraper.fetcher.requests.get")
    def test_deduplicates_slugs(self, mock_get, config):
        mock_get.return_value.json.return_value = [
            {"slug": "led-hacks", "name": "LED Hacks"},
            {"slug": "led-hacks", "name": "LED Hacks Duplicate"},
        ]
        mock_get.return_value.raise_for_status = Mock()
        result = fetch_available_categories(config)
        led = [(s, n) for s, n in result if s == "led-hacks"]
        assert len(led) == 1


# ---------------------------------------------------------------------------
# fetch_all_parallel
# ---------------------------------------------------------------------------

class TestFetchAllParallel:
    def test_empty_items(self, config):
        results = fetch_all_parallel([], lambda item, cfg, rl: item, config)
        assert results == []

    def test_all_succeed(self, config):
        items = [{"id": 1}, {"id": 2}, {"id": 3}]
        results = fetch_all_parallel(items, lambda item, cfg, rl: {"id": item["id"], "ok": True}, config)
        assert len(results) == 3
        ids = [r[0]["id"] for r in results]
        assert set(ids) == {1, 2, 3}

    def test_some_fail(self, config):
        items = [{"id": 1}, {"id": 2}, {"id": 3}]
        def fetch(item, cfg, rl):
            if item["id"] == 2:
                raise ValueError("fail")
            return {"id": item["id"], "ok": True}
        results = fetch_all_parallel(items, fetch, config)
        successes = [r for r in results if r[2] is None]
        failures = [r for r in results if r[2] is not None]
        assert len(successes) == 2
        assert len(failures) == 1
        assert "fail" in failures[0][2]

    def test_all_fail(self, config):
        items = [{"id": 1}, {"id": 2}]
        results = fetch_all_parallel(items, lambda item, cfg, rl: (_ for _ in ()).throw(ValueError("err")), config)
        assert all(r[2] is not None for r in results)

    def test_progress_callback(self, config):
        items = [{"id": 1}, {"id": 2}, {"id": 3}]
        callback = Mock()
        fetch_all_parallel(items, lambda item, cfg, rl: item, config, progress_callback=callback)
        assert callback.call_count == 3


# ---------------------------------------------------------------------------
# _scrape_article_worker (from main)
# ---------------------------------------------------------------------------

class TestScrapeArticleWorker:
    @patch("main._fetch_article_full")
    def test_success(self, mock_fetch):
        mock_fetch.return_value = {
            "url": "https://hackaday.com/x/",
            "html": "<html></html>",
            "author": "Test Author",
            "content_md": "**content**",
            "comments": [],
            "has_comments": False,
        }
        config = Mock()
        rate_limiter = Mock()
        article_row = {"id": 42, "url": "https://hackaday.com/x/"}
        from main import _scrape_article_worker
        result = _scrape_article_worker(article_row, config, rate_limiter)
        assert result["success"] is True
        assert result["id"] == 42
        assert result["author"] == "Test Author"
        assert result["content_md"] == "**content**"

    @patch("main._fetch_article_full")
    def test_failure(self, mock_fetch):
        mock_fetch.side_effect = ValueError("network error")
        config = Mock()
        rate_limiter = Mock()
        article_row = {"id": 99, "url": "https://hackaday.com/fail/"}
        from main import _scrape_article_worker
        result = _scrape_article_worker(article_row, config, rate_limiter)
        assert result["success"] is False
        assert result["id"] == 99
        assert "network error" in result["error"]

    @patch("main._fetch_article_full")
    def test_no_content_md_when_no_html(self, mock_fetch):
        mock_fetch.return_value = {
            "url": "https://hackaday.com/x/",
            "html": "<html></html>",
            "author": None,
            "content_md": None,
            "comments": [],
            "has_comments": False,
        }
        config = Mock()
        rate_limiter = Mock()
        article_row = {"id": 1, "url": "https://hackaday.com/x/"}
        from main import _scrape_article_worker
        result = _scrape_article_worker(article_row, config, rate_limiter)
        assert result["success"] is True
        assert result["content_md"] is None