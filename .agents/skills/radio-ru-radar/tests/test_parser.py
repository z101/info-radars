import pytest

from scraper.parser import (
    detect_format_type,
    make_excerpt_url,
    make_month_url,
    parse_content_page,
    parse_content_page_archive,
    parse_excerpt_page,
    parse_excerpt_page_archive,
    extract_pdf_url,
    decrement_month,
    validate_year_month,
)


class TestMakeMonthUrl:
    def test_new_format_single_digit(self):
        assert make_month_url(2026, 4) == "http://www.radio.ru/arhiv/2026/4.shtml"

    def test_new_format_double_digit(self):
        assert make_month_url(2025, 10) == "http://www.radio.ru/arhiv/2025/10.shtml"

    def test_new_format_january(self):
        assert make_month_url(2026, 1) == "http://www.radio.ru/arhiv/2026/1.shtml"

    def test_old_format_single_digit(self):
        assert make_month_url(2009, 1) == "http://www.radio.ru/archive/2009/01/"

    def test_old_format_double_digit(self):
        assert make_month_url(1995, 12) == "http://www.radio.ru/archive/1995/12/"

    def test_old_format_2005(self):
        assert make_month_url(2005, 6) == "http://www.radio.ru/archive/2005/06/"

    def test_transition_year_2009(self):
        assert make_month_url(2009, 12) == "http://www.radio.ru/archive/2009/12/"

    def test_transition_year_2010(self):
        assert make_month_url(2010, 1) == "http://www.radio.ru/arhiv/2010/1.shtml"


class TestMakeExcerptUrl:
    def test_basic(self):
        assert make_excerpt_url(2005, 1, 5) == "http://www.radio.ru/archive/2005/01/a5.shtml"

    def test_double_digit_month(self):
        assert make_excerpt_url(2009, 12, 42) == "http://www.radio.ru/archive/2009/12/a42.shtml"

    def test_article_id_zero(self):
        assert make_excerpt_url(1995, 6, 0) == "http://www.radio.ru/archive/1995/06/a0.shtml"


class TestDetectFormatType:
    def test_new_format(self):
        assert detect_format_type(2026) == "new"
        assert detect_format_type(2015) == "new"
        assert detect_format_type(2010) == "new"

    def test_old_pdf(self):
        assert detect_format_type(2009) == "old_pdf"

    def test_old_djvu(self):
        assert detect_format_type(2005) == "old_djvu"
        assert detect_format_type(2008) == "old_djvu"

    def test_old_annotation(self):
        assert detect_format_type(2002) == "old_annotation"
        assert detect_format_type(2004) == "old_annotation"

    def test_old_toc(self):
        assert detect_format_type(1994) == "old_toc"
        assert detect_format_type(2001) == "old_toc"


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


class TestParseContentPageNew:
    def test_parses_articles(self, sample_content_october_2025):
        articles = parse_content_page(sample_content_october_2025, year=2025)
        assert len(articles) == 5

    def test_article_fields(self, sample_content_october_2025):
        articles = parse_content_page(sample_content_october_2025, year=2025)
        a = articles[0]
        assert a["author"] == "А. ГОЛЫШКО"
        assert "Улучшая 5G" in a["topic"]
        assert a["page"] == "4"
        assert "d3b87ed2c2fe4b640ddb8c91547118d1" in a["detail_url"]

    def test_multiple_sections(self, sample_content_october_2025):
        articles = parse_content_page(sample_content_october_2025, year=2025)
        assert articles[0]["section"] == "Наука и техника"
        assert articles[1]["section"] == "Наука и техника"
        assert articles[2]["section"] == "Радиоприем"

    def test_second_article(self, sample_content_october_2025):
        articles = parse_content_page(sample_content_october_2025, year=2025)
        a = articles[1]
        assert a["author"] == "Я. БЛАГУШИН"
        assert a["page"] == "8"

    def test_page_numbers(self, sample_content_october_2025):
        articles = parse_content_page(sample_content_october_2025, year=2025)
        pages = [a["page"] for a in articles]
        assert pages == ["4", "8", "11", "13", "24"]

    def test_empty_content(self, sample_empty_content):
        articles = parse_content_page(sample_empty_content, year=2025)
        assert articles == []

    def test_april_2026(self, sample_content_april_2026):
        articles = parse_content_page(sample_content_april_2026, year=2026)
        assert len(articles) == 6
        assert articles[0]["topic"].startswith("Информация")
        assert articles[1]["author"] == "А. ГОЛЫШКО"
        assert "Сумерки" in articles[1]["topic"]
        assert articles[1]["section"] == "Наука и техника"
        assert articles[5]["page"] == "27"

    def test_has_d1_flag(self, sample_content_april_2026):
        articles = parse_content_page(sample_content_april_2026, year=2026)
        assert articles[1]["has_d1"] is True
        assert articles[2]["has_d1"] is False
        assert articles[4]["has_d1"] is True


class TestParseContentPageArchive:
    def test_1994_toc_only(self, sample_archive_toc_1994):
        articles = parse_content_page(sample_archive_toc_1994, year=1994)
        assert len(articles) >= 2
        for a in articles:
            assert a["has_d1"] is False
            assert a["has_d"] is False
            assert a["detail_url"] == ""

    def test_2002_annotation_only(self, sample_archive_annot_2002):
        articles = parse_content_page(sample_archive_annot_2002, year=2002)
        assert len(articles) >= 2
        for a in articles:
            assert a["has_d1"] is False
            assert a["format_type"] == "old_annotation"

    def test_2002_has_detail_url(self, sample_archive_annot_2002):
        articles = parse_content_page(sample_archive_annot_2002, year=2002)
        for a in articles:
            if a["has_d"]:
                assert a["detail_url"] != ""

    def test_2005_djvu(self, sample_archive_djvu_2005):
        articles = parse_content_page(sample_archive_djvu_2005, year=2005)
        assert len(articles) >= 2
        has_d1 = [a for a in articles if a["has_d1"]]
        assert len(has_d1) >= 1
        has_d_only = [a for a in articles if a["has_d"] and not a["has_d1"]]
        assert len(has_d_only) >= 1

    def test_2005_format_type(self, sample_archive_djvu_2005):
        articles = parse_content_page(sample_archive_djvu_2005, year=2005)
        for a in articles:
            assert a["format_type"] == "old_djvu"

    def test_2009_pdf(self, sample_archive_pdf_2009):
        articles = parse_content_page(sample_archive_pdf_2009, year=2009)
        has_d1 = [a for a in articles if a["has_d1"]]
        assert len(has_d1) >= 1


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


class TestParseExcerptPageArchive:
    def test_extracts_paragraphs(self):
        html = """<html><body>
<p><b>А. Петров.</b> Новая схема.</p>
<p>В этой статье описывается новая схема усилителя на транзисторах. Приведены практические рекомендации по настройке.</p>
<p><a href="http://ftp.radio.ru/pub/2005/01/5.pdf">Прочитать</a></p>
<p><a href="/archive/2005/01/">Вернуться назад</a></p>
</body></html>"""
        excerpt = parse_excerpt_page_archive(html)
        assert "новая схема усилителя" in excerpt
        assert "А. Петров" not in excerpt
        assert "Вернуться назад" not in excerpt


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