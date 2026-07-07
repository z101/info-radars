import pytest

from scraper.parser import (
    parse_content_page,
    parse_excerpt_page,
    extract_pdf_url,
    make_month_url,
    decrement_month,
    validate_year_month,
)


class TestMakeMonthUrl:
    def test_single_digit_month(self):
        assert make_month_url(2026, 4) == "http://www.radio.ru/arhiv/2026/4.shtml"

    def test_double_digit_month(self):
        assert make_month_url(2025, 10) == "http://www.radio.ru/arhiv/2025/10.shtml"

    def test_january(self):
        assert make_month_url(2026, 1) == "http://www.radio.ru/arhiv/2026/1.shtml"


class TestDecrementMonth:
    def test_normal_decrement(self):
        assert decrement_month(2026, 4) == (2026, 3)

    def test_january_rollover(self):
        assert decrement_month(2026, 1) == (2025, 12)

    def test_consecutive_rollover(self):
        y, m = decrement_month(2025, 1)
        assert (y, m) == (2024, 12)
        y, m = decrement_month(y, m)
        assert (y, m) == (2024, 11)


class TestValidateYearMonth:
    def test_valid(self):
        assert validate_year_month(2026, 4) is True
        assert validate_year_month(1924, 1) is True
        assert validate_year_month(2000, 12) is True

    def test_invalid(self):
        assert validate_year_month(2026, 0) is False
        assert validate_year_month(2026, 13) is False
        assert validate_year_month(1900, 1) is False
        assert validate_year_month(2101, 1) is False


class TestParseContentPage:
    def test_parses_articles(self, sample_content_october_2025):
        articles = parse_content_page(sample_content_october_2025)
        assert len(articles) == 5

    def test_article_fields(self, sample_content_october_2025):
        articles = parse_content_page(sample_content_october_2025)
        a = articles[0]
        assert a["author"] == "А. ГОЛЫШКО"
        assert "Улучшая 5G" in a["topic"]
        assert a["page"] == "4"
        assert "d3b87ed2c2fe4b640ddb8c91547118d1" in a["detail_url"]

    def test_multiple_sections(self, sample_content_october_2025):
        articles = parse_content_page(sample_content_october_2025)
        assert articles[0]["section"] == "Наука и техника"
        assert articles[1]["section"] == "Наука и техника"
        assert articles[2]["section"] == "Радиоприем"

    def test_second_article(self, sample_content_october_2025):
        articles = parse_content_page(sample_content_october_2025)
        a = articles[1]
        assert a["author"] == "Я. БЛАГУШИН"
        assert a["page"] == "8"

    def test_page_numbers(self, sample_content_october_2025):
        articles = parse_content_page(sample_content_october_2025)
        pages = [a["page"] for a in articles]
        assert pages == ["4", "8", "11", "13", "24"]

    def test_empty_content(self, sample_empty_content):
        articles = parse_content_page(sample_empty_content)
        assert articles == []

    def test_april_2026(self, sample_content_april_2026):
        articles = parse_content_page(sample_content_april_2026)
        assert len(articles) == 6
        assert articles[0]["topic"].startswith("Информация")
        assert articles[1]["author"] == "А. ГОЛЫШКО"
        assert "Сумерки" in articles[1]["topic"]
        assert articles[1]["section"] == "Наука и техника"
        assert articles[5]["page"] == "27"


class TestParseExcerptPage:
    def test_extracts_excerpt(self, sample_excerpt_html):
        excerpt = parse_excerpt_page(sample_excerpt_html)
        assert "подбора радиоэлементов" in excerpt
        assert "пьезокерамических фильтров" in excerpt
        assert "ЛОХНИ" not in excerpt

    def test_excerpt_no_return_link(self, sample_excerpt_html):
        excerpt = parse_excerpt_page(sample_excerpt_html)
        assert "Вернуться назад" not in excerpt

    def test_excerpt_no_pdf_text(self, sample_excerpt_html):
        excerpt = parse_excerpt_page(sample_excerpt_html)
        assert "Прочитать" not in excerpt

    def test_empty_page(self):
        excerpt = parse_excerpt_page("<html></html>")
        assert excerpt == ""


class TestExtractPdfUrl:
    def test_extracts_pdf(self, sample_excerpt_with_pdf_html):
        pdf_url = extract_pdf_url(sample_excerpt_with_pdf_html)
        assert pdf_url == "http://ftp.radio.ru/pub/2025/10/4.pdf"

    def test_no_pdf(self, sample_excerpt_html):
        pdf_url = extract_pdf_url(sample_excerpt_html)
        assert pdf_url == "http://ftp.radio.ru/pub/2025/10/13.pdf"

    def test_empty(self):
        pdf_url = extract_pdf_url("<html></html>")
        assert pdf_url == ""