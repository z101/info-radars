import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

BASE_URL = "http://www.radio.ru"

FORMAT_THRESHOLD = 2010


def make_month_url(year: int, month: int) -> str:
    if year >= FORMAT_THRESHOLD:
        return f"{BASE_URL}/arhiv/{year}/{month}.shtml"
    return f"{BASE_URL}/archive/{year}/{month:02d}/"


def make_excerpt_url(year: int, month: int, article_id: int) -> str:
    return f"{BASE_URL}/archive/{year}/{month:02d}/a{article_id}.shtml"


def decrement_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def validate_year_month(year: int, month: int) -> bool:
    return 1924 <= year <= 2100 and 1 <= month <= 12


def detect_format_type(year: int) -> str:
    if year >= FORMAT_THRESHOLD:
        return "new"
    if year >= 2009:
        return "old_pdf"
    if year >= 2005:
        return "old_djvu"
    if year >= 2002:
        return "old_annotation"
    return "old_toc"


def _abs_url(href: str) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return urljoin(BASE_URL, href)


def _has_d1_icon(td: Tag) -> bool:
    imgs = td.find_all("img", src=re.compile(r"d1\.(gif|png)$", re.I))
    return len(imgs) > 0


def _has_d_icon(td: Tag) -> bool:
    imgs = td.find_all("img", src=re.compile(r"d\.(gif|png)$", re.I))
    return len(imgs) > 0


# ---------------------------------------------------------------------------
# New format (2010+, /arhiv/YYYY/M.shtml, UTF-8, <table class="t_sod">)
# ---------------------------------------------------------------------------

def _tr_is_section(tr: Tag) -> bool:
    tds = tr.find_all("td", recursive=False)
    if not tds:
        return False
    style = tds[0].get("style", "")
    if "column-span: 2" not in style and tds[0].get("colspan") != "2":
        return False
    b = tds[0].find("b")
    return b is not None


def _tr_is_article(tr: Tag) -> bool:
    tds = tr.find_all("td", recursive=False)
    if len(tds) < 2:
        return False
    b = tds[0].find("b")
    if not b:
        return False
    bt = b.get_text(strip=True)
    if not bt.endswith("."):
        return False
    if not re.match(r"^[A-ZА-ЯЁ]\.", bt):
        return False
    return True


def _tr_is_info(tr: Tag) -> bool:
    tds = tr.find_all("td", recursive=False)
    if not tds:
        return False
    text = tds[0].get_text(strip=True)
    return text.startswith("Информация")


def _extract_section_name(tr: Tag) -> str:
    tds = tr.find_all("td", recursive=False)
    b = tds[0].find("b")
    return b.get_text(strip=True) if b else ""


def _extract_article(tr: Tag) -> dict:
    tds = tr.find_all("td", recursive=False)
    first_td = tds[0]
    second_td = tds[1]

    b = first_td.find("b")
    author = b.get_text(strip=True).rstrip(".") if b else ""

    a_tag = first_td.find("a", href=True)
    detail_url = _abs_url(a_tag["href"]) if a_tag else ""

    topic_html = str(first_td)
    topic = ""
    if b:
        after_b = topic_html.split(str(b), 1)
        if len(after_b) > 1:
            after_b_str = after_b[1]
            if a_tag:
                a_str = str(a_tag)
                aidx = after_b_str.find(a_str)
                if aidx >= 0:
                    topic = after_b_str[:aidx]
                else:
                    topic = after_b_str
            else:
                topic = after_b_str
            topic = BeautifulSoup(topic, "lxml").get_text(strip=True)
            topic = topic.rstrip(".,; \t&nbsp;")

    page = second_td.get_text(strip=True)

    has_d1 = _has_d1_icon(first_td)
    has_d = _has_d_icon(first_td)

    return {
        "author": author,
        "topic": topic,
        "page": page,
        "detail_url": detail_url,
        "has_d1": has_d1,
        "has_d": has_d,
        "format_type": "new",
    }


def parse_content_page_new(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")

    header = soup.find(
        lambda t: t.name in ("h3", "h4") and "Содержание номера" in t.get_text()
    )
    if not header:
        return []

    table = header.find_next("table", class_="t_sod")
    if not table:
        return []

    current_section = ""
    results = []

    for tr in table.find_all("tr", recursive=False):
        if _tr_is_section(tr):
            name = _extract_section_name(tr)
            if name and name not in ("—", "–", "-"):
                current_section = name
            continue

        if _tr_is_info(tr):
            tds = tr.find_all("td", recursive=False)
            first_td = tds[0]
            a_tag = first_td.find("a", href=True)
            detail_url = _abs_url(a_tag["href"]) if a_tag else ""
            page = tds[1].get_text(strip=True) if len(tds) > 1 else ""
            text = first_td.get_text(strip=True)
            has_d1 = _has_d1_icon(first_td)
            has_d = _has_d_icon(first_td)
            results.append({
                "section": "",
                "author": "",
                "topic": text,
                "page": page,
                "detail_url": detail_url,
                "has_d1": has_d1,
                "has_d": has_d,
                "format_type": "new",
            })
            continue

        if _tr_is_article(tr):
            article = _extract_article(tr)
            article["section"] = current_section
            results.append(article)
            continue

    return results


# ---------------------------------------------------------------------------
# Old format (1994–2012, /archive/YYYY/MM/, KOI8-R)
# ---------------------------------------------------------------------------

def _extract_article_archive_line(line_td: Tag) -> dict:
    b = line_td.find("b")
    author = b.get_text(strip=True).rstrip(".") if b else ""

    a_tag = line_td.find("a", href=True)
    detail_url = ""
    article_id = 0
    has_d1 = False
    has_d = False

    if a_tag:
        href = a_tag.get("href", "")
        if "javascript:opendescription" in href:
            m = re.search(r'opendescription\s*\(\s*(\d+)\s*\)', href)
            if m:
                article_id = int(m.group(1))
        detail_url = _abs_url(href)
        img = a_tag.find("img")
        if img:
            src = img.get("src", "")
            has_d1 = bool(re.search(r"d1\.(gif|png)$", src, re.I))
            has_d = bool(re.search(r"d\.(gif|png)$", src, re.I))

    topic = ""
    if b:
        after_b = str(line_td).split(str(b), 1)
        if len(after_b) > 1:
            after_b_str = after_b[1]
            if a_tag:
                a_str = str(a_tag)
                aidx = after_b_str.find(a_str)
                if aidx >= 0:
                    topic = after_b_str[:aidx]
                else:
                    topic = after_b_str
            else:
                topic = after_b_str
            topic = BeautifulSoup(topic, "lxml").get_text(strip=True)
            topic = topic.rstrip(".,; \t&nbsp;")
    else:
        text = line_td.get_text(strip=True)
        topic = text

    return {
        "author": author,
        "topic": topic,
        "detail_url": detail_url,
        "article_id": article_id,
        "has_d1": has_d1,
        "has_d": has_d,
    }


def parse_content_page_archive(html: str, year: int) -> list[dict]:
    fmt = detect_format_type(year)
    soup = BeautifulSoup(html, "lxml")

    content_table = soup.find(
        lambda t: t.name == "table"
        and t.find(lambda td: td.name == "td" and "Содержание номера" in td.get_text())
    )
    if content_table:
        article_table = content_table.find("table")
    else:
        header = soup.find(
            lambda t: t.name in ("h3", "h4") and "Содержание номера" in t.get_text()
        )
        if header:
            article_table = header.find_next("table")
        else:
            article_table = None

    if not article_table:
        return []

    current_section = ""
    results = []
    page_override = ""

    for tr in article_table.find_all("tr", recursive=False):
        tds = tr.find_all("td", recursive=False)
        if not tds:
            continue

        first_td = tds[0]
        second_td = tds[-1] if len(tds) > 1 else None
        text = first_td.get_text(strip=True)

        if not text:
            continue

        is_section = False
        b = first_td.find("b")
        if b and len(tds) == 1:
            name = b.get_text(strip=True)
            if name and not name.endswith(".") and not re.match(r"^[А-Я]\.", name):
                current_section = name
                is_section = True

        if is_section:
            continue

        has_d1 = _has_d1_icon(first_td)
        has_d = _has_d_icon(first_td)

        if not has_d and not has_d1 and not b and len(tds) == 2:
            page_override = second_td.get_text(strip=True) if second_td else ""
            results.append({
                "section": current_section,
                "author": "",
                "topic": text,
                "page": page_override,
                "detail_url": "",
                "has_d1": False,
                "has_d": False,
                "format_type": fmt,
            })
            continue

        if not has_d and not has_d1 and not b:
            continue

        article = _extract_article_archive_line(first_td)
        if not article["topic"] and not article["author"]:
            article["topic"] = text
        page = second_td.get_text(strip=True) if second_td else page_override
        results.append({
            "section": current_section,
            "author": article["author"],
            "topic": article["topic"],
            "page": page,
            "detail_url": article["detail_url"],
            "has_d1": article["has_d1"],
            "has_d": article["has_d"],
            "article_id": article["article_id"],
            "format_type": fmt,
        })

    return results


def parse_content_page(html: str, url: str = "", year: int = 0) -> list[dict]:
    if url and "arhiv/" in url:
        return parse_content_page_new(html)
    if year >= FORMAT_THRESHOLD:
        return parse_content_page_new(html)
    if year > 0:
        return parse_content_page_archive(html, year)
    if "archive/" in url:
        y_m = re.search(r"/archive/(\d{4})/\d{2}/", url)
        if y_m:
            return parse_content_page_archive(html, int(y_m.group(1)))
    if "arhiv/" in url:
        return parse_content_page_new(html)
    result = parse_content_page_new(html)
    if result:
        return result
    return parse_content_page_archive(html, 2000)


# ---------------------------------------------------------------------------
# Excerpt parsing
# ---------------------------------------------------------------------------

def parse_excerpt_page(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")

    header = soup.find(
        lambda t: t.name in ("h3", "h4") and "Аннотация статьи" in t.get_text()
    )
    if not header:
        return ""

    paragraphs = []
    found_first = False
    for sibling in header.find_next_siblings():
        txt = sibling.get_text(strip=True)
        if not txt:
            continue
        if "Вернуться назад" in txt:
            break
        if "Прочитать" in txt:
            break
        if not found_first:
            found_first = True
            continue
        paragraphs.append(txt)

    return "\n\n".join(paragraphs).strip()


def parse_excerpt_page_archive(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")

    paragraphs = soup.find_all("p")
    texts = []
    for p in paragraphs:
        txt = p.get_text(strip=True)
        if not txt:
            continue
        if any(skip in txt for skip in ("Прочитать", "Вернуться назад", "Вернуться", "Описание")):
            continue
        b = p.find("b")
        if b and b.get_text(strip=True).endswith("."):
            continue
        if txt.strip():
            texts.append(txt)
    return "\n\n".join(texts).strip() if texts else ""


def extract_pdf_url(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    pdf_link = soup.find("a", href=re.compile(r"\.pdf$"))
    if pdf_link:
        href = pdf_link["href"]
        if href.startswith("http"):
            return href
        return "http://ftp.radio.ru" + href if href.startswith("/") else href

    djvu_link = soup.find("a", href=re.compile(r"\.djvu$", re.I))
    if djvu_link:
        href = djvu_link["href"]
        if href.startswith("http"):
            return href
        return urljoin(BASE_URL, href)

    return ""