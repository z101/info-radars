import pytest
from bs4 import BeautifulSoup

from main import _clean_content, _make_markdown_converter
from scraper.parser import (
    _parse_comment,
    _parse_date,
    get_first_page_info,
    parse_archive_page,
    parse_article_page,
    validate_articles,
)


class TestMakeMarkdownConverter:
    def test_returns_html2text_instance(self):
        h = _make_markdown_converter()
        assert h.body_width == 0
        assert h.ignore_links is False
        assert h.ignore_images is False
        assert h.ignore_emphasis is False
        assert h.protect_links is True
        assert h.unicode_snob is True
        assert h.skip_internal_links is True
        assert h.inline_links is True


class TestCleanContent:
    def test_basic_paragraph(self):
        result = _clean_content("<p>Hello <b>world</b></p>")
        assert "Hello" in result
        assert "world" in result

    def test_strips_whitespace(self):
        result = _clean_content("  <p>Content</p>  \n")
        assert result == "Content"

    def test_empty_and_only_tags(self):
        assert _clean_content("") == ""
        assert _clean_content("<div><span></span></div>") == ""

    def test_links_and_images_preserved(self):
        result = _clean_content('<a href="https://example.com">link</a>')
        assert "example.com" in result or "link" in result
        result = _clean_content('<img src="pic.jpg" alt="photo">')
        assert "pic.jpg" in result or "photo" in result


class TestParseDate:
    @pytest.mark.parametrize("input_date,expected", [
        ("January 15, 2024", "2024-01-15"),
        ("March 5, 2023", "2023-03-05"),
        ("December 25, 2022", "2022-12-25"),
        ("", ""),
        ("not a date", ""),
    ])
    def test_parse_date(self, input_date, expected):
        assert _parse_date(input_date) == expected


class TestParseArchivePage:
    def test_returns_correct_count(self, sample_archive_html):
        articles = parse_archive_page(sample_archive_html)
        assert len(articles) == 3

    def test_returns_required_fields(self, sample_archive_html):
        articles = parse_archive_page(sample_archive_html)
        for a in articles:
            assert isinstance(a["title"], str) and a["title"]
            assert a["url"].startswith("https://hackaday.com/")
            assert isinstance(a["date"], str)
            assert isinstance(a["excerpt"], str)
            assert isinstance(a["tags"], list)

    def test_article_content(self, sample_archive_html):
        articles = parse_archive_page(sample_archive_html)
        assert articles[0]["title"] == "Test LED PWM Fading Article"
        assert articles[0]["date"] == "2024-01-15"
        assert articles[0]["tags"] == ["led", "pwm"]
        assert articles[1]["title"] == "WS2812B Addressable LED Strip Project"
        assert articles[1]["date"] == "2024-02-20"
        assert articles[2]["title"] == "555 Timer LED Flasher Circuits"
        assert articles[2]["date"] == "2023-11-05"

    def test_empty_html_and_no_articles(self):
        assert parse_archive_page("<html></html>") == []
        html = "<html><body><main class='site-main'></main></body></html>"
        assert parse_archive_page(html) == []

    def test_article_without_title_link_skipped(self):
        html = """
        <html><body><main class='site-main'>
        <article><header><h1 class="entry-title">No Link</h1></header></article>
        <article><header><h1 class="entry-title"><a href="https://hackaday.com/x/">Valid</a></h1></header>
        <div class="entry-content"><p>Content</p></div></article>
        </main></body></html>
        """
        articles = parse_archive_page(html)
        assert len(articles) == 1
        assert articles[0]["title"] == "Valid"

    @pytest.mark.parametrize("field,override,expected", [
        ("date", "<article><header><h1 class='entry-title'><a href='https://hackaday.com/x/'>X</a></h1></header><div class='entry-content'><p>C</p></div></article>", ""),
        ("excerpt", "<article><header><h1 class='entry-title'><a href='https://hackaday.com/x/'>X</a></h1></header></article>", ""),
        ("tags", "<article><header><h1 class='entry-title'><a href='https://hackaday.com/x/'>X</a></h1></header><div class='entry-content'><p>C</p></div></article>", []),
    ])
    def test_missing_field_defaults(self, field, override, expected):
        html = f"<html><body><main class='site-main'>{override}</main></body></html>"
        articles = parse_archive_page(html)
        assert articles[0][field] == expected


class TestGetFirstPageInfo:
    def test_returns_total_and_per_page(self, sample_archive_html):
        soup = BeautifulSoup(sample_archive_html, "html.parser")
        total, per_page = get_first_page_info(soup)
        assert total == 1935
        assert per_page == 3

    def test_no_counter(self):
        soup = BeautifulSoup("<html></html>", "html.parser")
        total, per_page = get_first_page_info(soup)
        assert total == 0
        assert per_page == 1

    def test_no_articles_returns_per_page_1(self):
        html = "<html><body><h2 class='counter_cat'>100 Articles</h2></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        total, per_page = get_first_page_info(soup)
        assert total == 100
        assert per_page == 1

    def test_counter_without_number(self):
        html = "<html><body><h2 class='counter_cat'>No number here</h2><article>a</article></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        total, per_page = get_first_page_info(soup)
        assert total == 0
        assert per_page == 1


class TestParseArticlePage:
    def test_author(self, sample_article_html):
        result = parse_article_page(sample_article_html)
        assert result["author"] == "Test Author"

    def test_no_author(self, sample_article_no_author_html):
        result = parse_article_page(sample_article_no_author_html)
        assert result["author"] is None

    def test_content_html_and_junk_stripping(self, sample_article_html):
        result = parse_article_page(sample_article_html)
        assert result["content_html"] is not None
        assert "LED brightness" in result["content_html"]
        assert "skip this" not in result["content_html"]
        assert "skip this too" not in result["content_html"]

    def test_no_content(self):
        html = "<html><body><p>No entry-content div</p></body></html>"
        result = parse_article_page(html)
        assert result["content_html"] is None

    def test_comments(self, sample_article_html):
        result = parse_article_page(sample_article_html)
        assert result["has_comments_section"] is True
        assert len(result["comments"]) == 2
        assert result["comments"][0]["author"] == "John Doe"
        assert result["comments"][1]["author"] == "Jane Smith"

    def test_no_comments(self):
        html = "<html><body><p>No comments here</p></body></html>"
        result = parse_article_page(html)
        assert result["has_comments_section"] is False
        assert result["comments"] == []

    def test_disqus_comments(self, sample_article_disqus_html):
        result = parse_article_page(sample_article_disqus_html)
        assert result["has_comments_section"] is True
        assert result["comments"] == []

    def test_parse_comment_exception_returns_none(self):
        li = BeautifulSoup("<li>bad</li>", "html.parser").find("li")
        result = _parse_comment(li)
        assert result is None


class TestValidateArticles:
    def test_valid_articles(self, sample_archive_html):
        articles = parse_archive_page(sample_archive_html)
        errors = validate_articles(articles)
        assert errors == []

    @pytest.mark.parametrize("article,keyword", [
        ({"title": "", "url": "https://hackaday.com/x/", "date": "x", "excerpt": "x", "tags": []}, "title"),
        ({"title": "x", "url": "https://evil.com/", "date": "x", "excerpt": "x", "tags": []}, "URL"),
        ({"title": "x", "url": "https://hackaday.com/x/", "date": "", "excerpt": "x", "tags": []}, "date"),
        ({"title": "x", "url": "https://hackaday.com/x/", "date": "x", "excerpt": "", "tags": []}, "excerpt"),
    ])
    def test_field_validation(self, article, keyword):
        errors = validate_articles([article])
        assert any(keyword in e for e in errors)

    def test_multiple_errors(self):
        articles = [
            {"title": "", "url": "https://evil.com/", "date": "", "excerpt": "", "tags": []},
            {"title": "ok", "url": "https://hackaday.com/x/", "date": "x", "excerpt": "x", "tags": []},
        ]
        errors = validate_articles(articles)
        assert len(errors) >= 2

    def test_tags_not_validated_as_required(self):
        articles = [{"title": "x", "url": "https://hackaday.com/x/", "date": "x", "excerpt": "x", "tags": None}]
        errors = validate_articles(articles)
        assert errors == []
