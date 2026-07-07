import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

BASE_URL = "http://www.radio.ru"


def make_month_url(year: int, month: int) -> str:
    return f"{BASE_URL}/arhiv/{year}/{month}.shtml"


def decrement_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def validate_year_month(year: int, month: int) -> bool:
    return 1924 <= year <= 2100 and 1 <= month <= 12


def _abs_url(href: str) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return urljoin(BASE_URL, href)


def _tr_is_section(tr: Tag) -> bool:
    """Check if a <tr> is a section header (colspan=2, centered bold text)."""
    tds = tr.find_all("td", recursive=False)
    if not tds:
        return False
    style = tds[0].get("style", "")
    if "column-span: 2" not in style and tds[0].get("colspan") != "2":
        return False
    b = tds[0].find("b")
    return b is not None


def _tr_is_article(tr: Tag) -> bool:
    """Check if a <tr> is an article row (td with <b>Author.</b> + page td)."""
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
    """Check if a <tr> is the info entry (empty <b>, no author pattern)."""
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
            topic = BeautifulSoup(topic, "html.parser").get_text(strip=True)
            topic = topic.rstrip(".,; \t&nbsp;")

    page = second_td.get_text(strip=True)

    return {
        "author": author,
        "topic": topic,
        "page": page,
        "detail_url": detail_url,
    }


def parse_content_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")

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
            results.append({
                "section": "",
                "author": "",
                "topic": text,
                "page": page,
                "detail_url": detail_url,
            })
            continue

        if _tr_is_article(tr):
            article = _extract_article(tr)
            article["section"] = current_section
            results.append(article)
            continue

    return results


def parse_excerpt_page(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

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
        # Skip first paragraph (repeats author/title), take second+
        if not found_first:
            found_first = True
            continue
        paragraphs.append(txt)

    return "\n\n".join(paragraphs).strip()


def extract_pdf_url(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    pdf_link = soup.find("a", href=re.compile(r"\.pdf$"))
    if pdf_link:
        href = pdf_link["href"]
        if href.startswith("http"):
            return href
        return "http://ftp.radio.ru" + href if href.startswith("/") else href
    return ""