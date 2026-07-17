import argparse
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

_src = Path(__file__).parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from analyzer.config import DEFAULT_ANALYZE_CONFIG
from analyzer.hashes import (
    compute_content_hash,
    compute_query_hash,
)
from analyzer.report import generate_report
from scraper.database import Database
from scraper.fetcher import (
    AdaptiveRateLimiter,
    RequestConfig,
    fetch_all_parallel,
    fetch_html,
)
from scraper.logging import setup_logging
from scraper.parser import (
    FORMAT_THRESHOLD,
    decrement_month,
    detect_format_type,
    extract_pdf_url,
    make_excerpt_url,
    make_month_url,
    parse_content_page,
    parse_excerpt_page,
    parse_excerpt_page_archive,
)
from xlsx_exporter import export_to_xlsx, import_from_xlsx

logger = logging.getLogger(__name__)

MAX_CONSECUTIVE_404 = 10
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent


def scrape_month(
    db: Database,
    year: int,
    month: int,
    session_id: int,
    request_cfg: RequestConfig,
    rate_limiter: AdaptiveRateLimiter,
    dry_run: bool = False,
    force: bool = False,
    force_format: str = "",
) -> int:
    if force_format == "archive":
        url = f"http://www.radio.ru/archive/{year}/{month:02d}/"
    elif force_format == "arhiv":
        url = f"http://www.radio.ru/arhiv/{year}/{month}.shtml"
    else:
        url = make_month_url(year, month)

    try:
        html = fetch_html(url, request_cfg, rate_limiter)
    except Exception as e:
        logger.debug("Failed to fetch %s: %s", url, e)
        if not dry_run:
            db.mark_month_error(year, month, session_id, str(e))
        return -1

    articles = parse_content_page(html, url=url, year=year)
    if not articles and not force_format:
        alt_url = None
        if "/arhiv/" in url:
            alt_url = f"http://www.radio.ru/archive/{year}/{month:02d}/"
        elif "/archive/" in url:
            alt_url = f"http://www.radio.ru/arhiv/{year}/{month}.shtml"
        if alt_url:
            try:
                alt_html = fetch_html(alt_url, request_cfg, rate_limiter)
                alt_articles = parse_content_page(alt_html, url=alt_url, year=year)
                if alt_articles:
                    articles = alt_articles
                    url = alt_url
                    logger.debug("Fallback to %s — %d articles", url, len(articles))
            except Exception:
                pass

    if not articles:
        logger.debug("No articles found on %s", url)
        if not dry_run:
            db.mark_month_done(year, month, session_id, 0)
        return 0

    logger.debug("Found %d articles in %s", len(articles), url)

    if dry_run:
        return len(articles)

    fmt = detect_format_type(year)
    now = datetime.now(timezone.utc).isoformat()

    db.upsert_articles_batch(articles, year, month, session_id, now, fmt)

    if force:
        for art in articles:
            db.update_article_metadata(
                year=year,
                month=month,
                section=art.get("section", ""),
                topic=art.get("topic", ""),
                author=art.get("author", ""),
                page=art.get("page", ""),
                detail_url=art.get("detail_url", ""),
            )

    db.mark_month_done(year, month, session_id, len(articles))
    return len(articles)


def _scrape_month_safe(
    db: Database,
    year: int,
    month: int,
    session_id: int,
    request_cfg: RequestConfig,
    rate_limiter: AdaptiveRateLimiter,
    dry_run: bool = False,
    force: bool = False,
    force_format: str = "",
) -> int:
    try:
        return scrape_month(
            db, year, month, session_id, request_cfg, rate_limiter,
            dry_run, force, force_format,
        )
    except Exception as e:
        logger.warning("Month %04d-%02d failed: %s", year, month, e)
        return -1


def auto_scan(
    db: Database,
    session_id: int,
    request_cfg: RequestConfig,
    rate_limiter: AdaptiveRateLimiter,
    start_year: int,
    start_month: int,
    max_404: int = MAX_CONSECUTIVE_404,
    with_excerpt: bool = False,
    dry_run: bool = False,
    force: bool = False,
    force_format: str = "",
) -> int:
    return auto_scan_parallel(
        db, session_id, request_cfg, rate_limiter,
        start_year, start_month, max_404, dry_run, force, force_format,
    )


def auto_scan_parallel(
    db: Database,
    session_id: int,
    request_cfg: RequestConfig,
    rate_limiter: AdaptiveRateLimiter,
    start_year: int,
    start_month: int,
    max_404: int = MAX_CONSECUTIVE_404,
    dry_run: bool = False,
    force: bool = False,
    force_format: str = "",
) -> int:
    workers = min(request_cfg.scan_parallel_months, 6)
    y, m = start_year, start_month
    consecutive_404 = 0
    consecutive_empty = 0
    total_found = 0
    total_months = 0
    max_empty = 25

    while consecutive_404 < max_404 and consecutive_empty < max_empty:
        batch = []
        scan_y, scan_m = y, m
        while len(batch) < workers:
            if not force:
                while db.is_month_scraped(scan_y, scan_m):
                    if scan_y < 1924:
                        break
                    scan_y, scan_m = decrement_month(scan_y, scan_m)
            if scan_y < 1924:
                break
            batch.append((scan_y, scan_m))
            scan_y, scan_m = decrement_month(scan_y, scan_m)
            if len(batch) >= 50:
                break

        if not batch:
            y, m = scan_y, scan_m
            continue

        batch_results = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(
                    _scrape_month_safe, db, by, bm, session_id,
                    request_cfg, rate_limiter, dry_run, force, force_format,
                ): (by, bm) for by, bm in batch
            }
            for future in as_completed(future_map):
                by, bm = future_map[future]
                batch_results.append((by, bm, future.result()))

        batch_results.sort(key=lambda x: (-x[0], -x[1]))
        for by, bm, result in batch_results:
            url = make_month_url(by, bm)
            if result == -1:
                consecutive_404 += 1
                consecutive_empty = 0
                if not dry_run:
                    db.mark_month_404(by, bm, session_id, consecutive_404)
                logger.info("ERR %04d-%02d - 404 (%d/%d) | %s", by, bm, consecutive_404, max_404, url)
                if consecutive_404 >= max_404:
                    break
            elif result == 0:
                if by < FORMAT_THRESHOLD:
                    consecutive_empty += 1
                else:
                    consecutive_empty = 0
                if not dry_run:
                    db.mark_month_done(by, bm, session_id, 0)
                consecutive_404 = 0
                logger.info("-- %04d-%02d - пусто | %s", by, bm, url)
            else:
                total_found += result
                total_months += 1
                consecutive_404 = 0
                consecutive_empty = 0
                logger.info("OK %04d-%02d - %d статей | %s", by, bm, result, url)

        if consecutive_404 >= max_404 or consecutive_empty >= max_empty:
            break

        y, m = scan_y, scan_m

        if not dry_run:
            db.finish_session(
                session_id, "running",
                total_months=total_months,
                total_found=total_found,
            )

    stop_reason = (
        f"{max_404} consecutive 404s" if consecutive_404 >= max_404
        else f"{max_empty} consecutive empty months (pre-2010 TOC)"
    )
    logger.info(
        "Auto-scan complete: %d months, %d articles, stopped after %s",
        total_months, total_found, stop_reason,
    )
    return total_found


def _make_excerpt_worker(year: int, month: int):
    def worker(article_row, cfg, rl):
        art_url = article_row["detail_url"]
        if not art_url:
            return {"topic": article_row["topic"], "excerpt": "", "pdf_url": ""}
        html = fetch_html(art_url, cfg, rl)
        if year >= FORMAT_THRESHOLD or "arhiv/" in art_url:
            excerpt = parse_excerpt_page(html)
            if not excerpt and "archive/" in art_url:
                excerpt = parse_excerpt_page_archive(html)
            pdf_url = extract_pdf_url(html)
        else:
            excerpt = parse_excerpt_page_archive(html)
            pdf_url = extract_pdf_url(html)
        return {"topic": article_row["topic"], "excerpt": excerpt, "pdf_url": pdf_url}
    return worker


def fetch_missing_excerpts(
    db: Database,
    session_id: int,
    request_cfg: RequestConfig,
    dry_run: bool = False,
) -> int:
    rows = db.get_months_without_excerpts()
    if not rows:
        logger.info("All excerpts already fetched.")
        return 0

    all_articles = []
    for row in rows:
        articles = db.get_articles_without_excerpt(row["year"], row["month"])
        for a in articles:
            a["_year"] = row["year"]
            a["_month"] = row["month"]
        all_articles.extend(articles)

    total = len(all_articles)
    if total == 0:
        logger.info("All excerpts already fetched.")
        return 0

    def _global_worker(article_row, cfg, rl):
        y = article_row["_year"]
        m = article_row["_month"]
        return _make_excerpt_worker(y, m)(article_row, cfg, rl)

    logger.info("Fetching %d excerpts from %d months ...", total, len(rows))
    start = time.time()

    results = fetch_all_parallel(all_articles, _global_worker, request_cfg)

    batch_items = []
    errors = 0
    for item, result, error in results:
        if error:
            logger.warning("Failed excerpt for %s: %s", item["topic"], error)
            errors += 1
            continue
        if result.get("excerpt"):
            batch_items.append((result["excerpt"], result["topic"],
                               item["_year"], item["_month"]))
        if result.get("pdf_url"):
            db.update_pdf_url(result["topic"], item["_year"], item["_month"],
                              result["pdf_url"])

    fetched = db.update_excerpts_batch(batch_items) if batch_items else 0
    elapsed = time.time() - start
    logger.info("Excerpts: %d/%d за %.1fс (%.1f статей/с)%s",
                fetched, total, elapsed, fetched / elapsed if elapsed > 0 else 0,
                f", {errors} ошибок" if errors else "")
    return fetched


def _fetch_single_month_excerpts(
    db: Database,
    year: int,
    month: int,
    request_cfg: RequestConfig,
    dry_run: bool = False,
) -> int:
    articles_to_fetch = db.get_articles_without_excerpt(year, month)
    if not articles_to_fetch:
        return 0
    logger.info("Fetching excerpts for %04d-%02d (%d articles) ...", year, month, len(articles_to_fetch))

    worker = _make_excerpt_worker(year, month)
    results = fetch_all_parallel(articles_to_fetch, worker, request_cfg)

    batch_items = []
    for item, result, error in results:
        if error:
            logger.warning("Failed excerpt for %s: %s", item["topic"], error)
            continue
        if result.get("excerpt"):
            batch_items.append((result["excerpt"], result["topic"], year, month))
        if result.get("pdf_url"):
            db.update_pdf_url(result["topic"], year, month, result["pdf_url"])

    updated = db.update_excerpts_batch(batch_items) if batch_items else 0
    logger.info("Fetched %d excerpts for %04d-%02d", updated, year, month)
    return updated


def show_summary(db: Database, json_output: bool = False):
    summary = db.get_summary()
    if json_output:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return

    print(f"\nRadio.ru archive status:")
    print(f"  Articles: {summary['total_articles']}")
    print(f"  Months:   {summary['total_months']}")
    if summary.get("year_range"):
        print(f"  Years:    {summary['year_range'][0]} - {summary['year_range'][1]}")
    if summary.get("earliest"):
        print(f"  Range:    {summary['earliest']} - {summary['latest']}")
    print(f"  With excerpt: {summary['with_excerpt']}")
    print(f"  With PDF/DjVu: {summary['with_pdf']}")
    if summary.get("format_breakdown"):
        print(f"  Format breakdown:")
        for fmt, cnt in sorted(summary["format_breakdown"].items()):
            print(f"    {fmt:20s}: {cnt}")
    print()


def show_latest(db: Database, limit: int, json_output: bool = False):
    articles = db.get_latest_articles(limit)
    if json_output:
        print(json.dumps(articles, indent=2, ensure_ascii=False, default=str))
        return

    if not articles:
        print("No articles in database.")
        return

    print(f"\nLatest {len(articles)} articles:")
    print()
    for a in articles:
        ym = f"{a['year']:04d}-{a['month']:02d}"
        section = f" [{a['section']}]" if a.get("section") else ""
        flags = ""
        if a.get("is_interesting"):
            flags += "[I]"
        if a.get("is_read"):
            flags += "[R]"
        print(f"  {ym} {a['topic']}{section} {flags}")
        if a.get("author"):
            print(f"    Author: {a['author']}  Page: {a.get('page', '?')}")
        if a.get("excerpt"):
            excerpt = a["excerpt"][:200] + "\u2026" if len(a["excerpt"]) > 200 else a["excerpt"]
            print(f"    {excerpt}")
        print()


# ---------------------------------------------------------------------------
# Search pipeline
# ---------------------------------------------------------------------------

def _load_query_file(path: str) -> tuple[str, str]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Query file not found: {path}")
    query_text = p.read_text(encoding="utf-8").strip()
    if not query_text:
        raise ValueError(f"Query file is empty: {path}")
    query_name = p.stem
    return query_name, query_text


def _resolve_hashes(args) -> tuple[str, str, str, dict]:
    query_name, query_text = _load_query_file(args.query_file)
    query_hash = compute_query_hash(query_text)
    cfg = DEFAULT_ANALYZE_CONFIG
    return query_name, query_text, query_hash, cfg


def _save_search_results(
    db: Database,
    results: list,
    query_hash: str,
) -> int:
    saved = 0
    errors = 0
    for item in results:
        article_id = item.get("id")
        if article_id is None:
            logger.warning("Skipping item without 'id': %s", item)
            continue

        row = db._fetchone(
            "SELECT excerpt, topic, author FROM articles WHERE id = ?", (article_id,)
        )
        if not row:
            logger.warning("Article id=%s not found in DB", article_id)
            continue

        content_hash = compute_content_hash(row["excerpt"], row["topic"] or "", row["author"] or "")

        if "error" in item:
            db.mark_search_error(
                article_id, query_hash, content_hash,
                str(item["error"]),
            )
            errors += 1
            continue

        relevance = item.get("score") or item.get("relevance", 0)
        reason = item.get("reason", "")
        db.save_search_result(
            article_id, query_hash, content_hash,
            relevance, reason,
        )
        saved += 1

    logger.info("Saved %d result(s), %d error(s)", saved, errors)
    if not saved and not errors:
        logger.info("No results to save.")
    return 0


def _scope_kwargs(args):
    """Extract scope filter kwargs from parsed args."""
    kw = {}
    if getattr(args, 'limit', None) is not None:
        kw["scope_limit"] = args.limit
    if getattr(args, 'since', None):
        sy, sm = _parse_search_date(args.since, is_since=True)
        kw["scope_since_year"] = sy
        kw["scope_since_month"] = sm
    if getattr(args, 'until', None):
        uy, um = _parse_search_date(args.until, is_since=False)
        kw["scope_until_year"] = uy
        kw["scope_until_month"] = um
    return kw


def _handle_search_init(args, db: Database) -> int:
    if not args.query_file:
        logger.error("--query-file is required")
        return 1

    query_name, query_text = _load_query_file(args.query_file)
    query_hash = compute_query_hash(query_text)

    scope_kw = _scope_kwargs(args)
    status = db.get_search_status(query_hash, **scope_kw)
    total = status["total_articles"]
    scored = status["by_status"].get("scored", 0)
    pending = total - scored

    batch_size = args.batch_size or 100
    batches = (pending + batch_size - 1) // batch_size if pending > 0 else 0

    scope_parts = []
    if args.limit:
        scope_parts.append(f"limit={args.limit}")
    if args.since:
        scope_parts.append(f"since={args.since}")
    if args.until:
        scope_parts.append(f"until={args.until}")
    scope_label = f" [{', '.join(scope_parts)}]" if scope_parts else ""

    if pending <= 0:
        print(f"\nAll {total} articles{scope_label} already searched for '{query_name}'.")
        print("Use: search report --query-file <path>")
        return 0

    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"\n=== SEARCH SESSION: {session_id} ===")
    print(f"Query: {query_name}")
    print(f"Scope: pending={pending}, total={total}, scored={scored}{scope_label}")
    print(f"Batch size: {batch_size}")
    print(f"Batches: {batches}")
    print()
    return 0


def _handle_search_get_batch(args, db: Database) -> int:
    if not args.query_file:
        logger.error("--query-file is required")
        return 1

    try:
        query_name, query_text, query_hash, cfg = _resolve_hashes(args)
    except (FileNotFoundError, ValueError) as e:
        logger.error("%s", e)
        return 1

    batch_size = args.batch_size or 100
    max_retries = 3
    scope_kw = _scope_kwargs(args)

    candidates = db.get_search_candidates_batch(
        query_hash, args.batch_index, batch_size, max_retries, **scope_kw,
    )
    articles = [{"id": a["id"], "text": format_article_text(a)} for a in candidates]
    print(json.dumps(articles, indent=None if args.compact else 2, ensure_ascii=False))
    return 0


def _handle_search_set_batch(args, db: Database) -> int:
    if not args.query_file:
        logger.error("--query-file is required")
        return 1

    try:
        query_name, query_text, query_hash, cfg = _resolve_hashes(args)
    except (FileNotFoundError, ValueError) as e:
        logger.error("%s", e)
        return 1

    # Load from file(s) or stdin
    if args.batch_file:
        results = []
        for fp in args.batch_file:
            path = Path(fp)
            if not path.is_absolute():
                path = (PROJECT_ROOT / fp).resolve()
            if not path.exists():
                logger.error("Batch file not found: %s", fp)
                return 1
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                logger.error("Invalid JSON in %s: %s", fp, e)
                return 1
            if not isinstance(data, list):
                logger.error("Expected a JSON array in %s", fp)
                return 1
            results.extend(data)
        return _save_search_results(db, results, query_hash)

    # Fallback: stdin
    try:
        raw = sys.stdin.read()
        if raw.startswith('\ufeff'):
            raw = raw[1:]
        results = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON from stdin: %s", e)
        return 1
    if not isinstance(results, list):
        logger.error("Expected a JSON array from stdin")
        return 1
    return _save_search_results(db, results, query_hash)


def _handle_search_status(args, db: Database) -> int:
    if not args.query_file:
        logger.error("--query-file is required")
        return 1

    try:
        query_name, query_text, query_hash, cfg = _resolve_hashes(args)
    except (FileNotFoundError, ValueError) as e:
        logger.error("%s", e)
        return 1

    scope_kw = _scope_kwargs(args)
    status = db.get_search_status(query_hash, **scope_kw)
    if args.json:
        print(json.dumps(status, indent=2, ensure_ascii=False))
    else:
        total = status["total_articles"]
        print(f"\nSearch status for query '{query_name}':")
        print(f"  Total articles in DB: {total}")
        for s, cnt in sorted(status["by_status"].items()):
            print(f"  {s:12s}: {cnt}")
    return 0


def _handle_search_report(args, db: Database) -> int:
    if not args.query_file:
        logger.error("--query-file is required")
        return 1

    try:
        query_name, query_text, query_hash, cfg = _resolve_hashes(args)
    except (FileNotFoundError, ValueError) as e:
        logger.error("%s", e)
        return 1

    csv_path = generate_report(
        db, query_name, query_hash,
        min_score=args.min_score or 0, top=args.top,
    )
    if csv_path is None:
        print(f"No scored results yet for query '{query_name}'.")
    return 0


def _handle_track(args, db: Database) -> int:
    print("Track mode is not implemented yet.")
    return 0


def _handle_summarize(args, db: Database) -> int:
    print("Summarize mode is not implemented yet.")
    return 0


def format_article_text(a: dict) -> str:
    """Format a single article to combined raw text for the searcher."""
    topic = a.get("topic", "")
    author = (a.get("author") or "").strip()
    section = (a.get("section") or "").strip()
    excerpt = (a.get("excerpt") or "").strip()

    ym = f"{a['year']:04d}-{a['month']:02d}"
    parts = f'[{ym}] "{topic}"'
    if author:
        parts += f" by {author}"
    if section:
        parts += f" [{section}]"
    if excerpt:
        parts += f" — {excerpt}"
    return parts


# ---------------------------------------------------------------------------
# Interesting / Read / XLSX
# ---------------------------------------------------------------------------

def _handle_interesting(args, db: Database) -> int:
    if args.mark_interesting:
        db.mark_interesting(args.mark_interesting)
        print(f"Marked {len(args.mark_interesting)} article(s) as interesting.")
        return 0

    if args.unmark_interesting:
        db.unmark_interesting(args.unmark_interesting)
        print(f"Unmarked {len(args.unmark_interesting)} article(s) as interesting.")
        return 0

    if args.mark_read:
        db.mark_read(args.mark_read)
        print(f"Marked {len(args.mark_read)} article(s) as read.")
        return 0

    if args.unmark_read:
        db.unmark_read(args.unmark_read)
        print(f"Unmarked {len(args.unmark_read)} article(s) as read.")
        return 0

    if args.list_interesting:
        articles = db.get_interesting_articles()
        if not articles:
            print("No interesting articles.")
            return 0
        for a in articles:
            ym = f"{a['year']:04d}-{a['month']:02d}"
            read_mark = "[R]" if a.get("is_read") else "   "
            print(f"[{a['id']}] [I]{read_mark} {a['topic']} ({ym})")
            print(f"       {a['detail_url']}")
            if a.get("excerpt"):
                print(f"       {a['excerpt'][:200]}")
            print()
        return 0

    if args.list_unread:
        articles = db.get_unread_articles()
        if not articles:
            print("All articles read.")
            return 0
        for a in articles:
            ym = f"{a['year']:04d}-{a['month']:02d}"
            interesting_mark = "[I]" if a.get("is_interesting") else "   "
            print(f"[{a['id']}] {interesting_mark}   {a['topic']} ({ym})")
            print(f"       {a['detail_url']}")
            if a.get("excerpt"):
                print(f"       {a['excerpt'][:200]}")
            print()
        return 0

    if args.export_xlsx:
        filter_mode = args.filter or "all"
        articles = db.get_articles_for_export(filter_mode)
        if not articles:
            print(f"No articles to export (filter={filter_mode}).")
            return 0
        today = datetime.now().strftime("%Y-%m-%d")
        reports_dir = Path("../../../reports/radio-ru-radar")
        reports_dir.mkdir(parents=True, exist_ok=True)
        output_path = reports_dir / f"articles_{today}.xlsx"
        export_to_xlsx(articles, str(output_path))
        print(f"Exported {len(articles)} articles to {output_path}")
        return 0

    if args.import_xlsx:
        result = import_from_xlsx(args.import_xlsx, db)
        print(f"Import complete: {result['total_rows']} rows processed.")
        print(f"  is_interesting updated: {result['updated_interesting']}")
        print(f"  is_read updated:        {result['updated_read']}")
        return 0

    return 0


# ---------------------------------------------------------------------------
# Parser / Main
# ---------------------------------------------------------------------------

def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape and analyze Radio.ru magazine archive",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s                                        # Auto-scan from current month\n"
            "  %(prog)s --year 2026 --month 4                   # Single month\n"
            "  %(prog)s --since 2025-01 --until 2026-04         # Range\n"
            "  %(prog)s --db-summary                            # DB status\n"
            "  %(prog)s --dry-run --year 2026 --month 4         # Validate without saving\n"
            "  %(prog)s --no-excerpt                            # Skip annotations\n"
            "  %(prog)s --year 2026 --month 4 --force           # Re-scrape month\n"
            "  %(prog)s search init --query-file <path>         # Search orchestrator\n"
            "  %(prog)s --export-xlsx                           # Export to Excel\n"
            "  %(prog)s --mark-interesting 5 12                 # Mark articles as interesting\n"
        ),
    )

    # --- Scraping options ---
    scrape = parser.add_argument_group("Scraping options")
    scrape.add_argument("--auto-scan", action="store_true",
                        help="Auto-scan backwards from current month (default)")
    scrape.add_argument("--year", type=int, metavar="YYYY", help="Year to scrape")
    scrape.add_argument("--month", type=int, metavar="M", help="Month to scrape (1-12)")
    scrape.add_argument("--since", type=str, metavar="YYYY-MM", help="Start date (inclusive)")
    scrape.add_argument("--until", type=str, metavar="YYYY-MM", help="End date (inclusive)")
    scrape.add_argument("--no-excerpt", action="store_true", help="Skip fetching article annotations")
    scrape.add_argument("--force-excerpt", action="store_true", help="Re-fetch missing excerpts for all scraped months")
    scrape.add_argument("--force", action="store_true", help="Re-scrape metadata & excerpts for already-scraped months")
    scrape.add_argument("--max-404", type=int, default=MAX_CONSECUTIVE_404,
                        metavar="N", help=f"Stop after N consecutive 404s (default: {MAX_CONSECUTIVE_404})")
    scrape.add_argument("--dry-run", action="store_true", help="Validate only, no save")
    scrape.add_argument("--archive", action="store_true",
                        help="Force old /archive/YYYY/MM/ URL format (pre-2010)")
    scrape.add_argument("--arhiv", action="store_true",
                        help="Force new /arhiv/YYYY/M.shtml URL format (2010+)")

    # --- Information options ---
    info = parser.add_argument_group("Information options")
    info.add_argument("--db-summary", action="store_true", help="Show database summary")
    info.add_argument("--db-schema", action="store_true", help="Show database schema")
    info.add_argument("--latest", type=int, metavar="N", help="Show N most recent articles")
    info.add_argument("--db-search", type=str, metavar="KEYWORD", help="Search articles by keyword")

    # --- Subcommands ---
    subparsers = parser.add_subparsers(dest="mode", help="Analysis mode")

    # === search ===
    search_parser = subparsers.add_parser("search", help="Semantic search via searcher subagents")
    search_sub = search_parser.add_subparsers(dest="command", help="Search command")

    search_common = argparse.ArgumentParser(add_help=False)
    search_common.add_argument("--query-file", type=str, metavar="PATH", required=True,
                               help="Path to a query file")

    search_init = search_sub.add_parser("init", parents=[search_common],
                                        help="Initialize search session (orchestrator)")
    search_init.add_argument("--batch-size", type=int, default=100, metavar="N",
                             help="Batch size (default: 100)")
    search_init.add_argument("--limit", type=int, metavar="N",
                             help="Limit candidates to N most recent articles")
    search_init.add_argument("--since", type=str, metavar="YYYY-MM",
                             help="Search from this date")
    search_init.add_argument("--until", type=str, metavar="YYYY-MM",
                             help="Search up to this date")

    search_get = search_sub.add_parser("get-batch", parents=[search_common],
                                       help="Get batch data as JSON [{id, text}]")
    search_get.add_argument("batch_index", type=int, metavar="INDEX",
                            help="Batch index")
    search_get.add_argument("--batch-size", type=int, default=100, metavar="N",
                            help="Batch size (default: 100)")
    search_get.add_argument("--limit", type=int, metavar="N",
                            help="Limit candidates to N most recent articles")
    search_get.add_argument("--since", type=str, metavar="YYYY-MM",
                            help="Search from this date")
    search_get.add_argument("--until", type=str, metavar="YYYY-MM",
                            help="Search up to this date")
    search_get.add_argument("--compact", action="store_true",
                            help="Output compact JSON (one line per article)")

    search_set = search_sub.add_parser("set-batch", parents=[search_common],
                                       help="Save batch results [{id, score, reason}]")
    search_set.add_argument("--batch-file", type=str, metavar="PATH", action="append",
                            help="Read results from file(s) (repeatable; stdin fallback)")

    search_status = search_sub.add_parser("status", parents=[search_common],
                                          help="Show search progress")
    search_status.add_argument("--json", action="store_true", help="Output as JSON")
    search_status.add_argument("--limit", type=int, metavar="N",
                               help="Limit candidates to N most recent articles")
    search_status.add_argument("--since", type=str, metavar="YYYY-MM",
                               help="Search from this date")
    search_status.add_argument("--until", type=str, metavar="YYYY-MM",
                               help="Search up to this date")

    search_report = search_sub.add_parser("report", parents=[search_common],
                                          help="Generate ranked search report (XLSX)")
    search_report.add_argument("--top", type=int, metavar="N", help="Limit report to top N")
    search_report.add_argument("--min-score", type=int, default=0, metavar="N",
                               help="Minimum relevance score")

    # === track (stub) ===
    track_parser = subparsers.add_parser("track", help="Detect trends and anomalies (not implemented)")
    track_parser.add_argument("--query-file", type=str, metavar="PATH", help="Path to a query file")

    # === summarize (stub) ===
    sum_parser = subparsers.add_parser("summarize", help="Summarize articles (not implemented)")
    sum_parser.add_argument("--query-file", type=str, metavar="PATH", help="Path to a query file")

    # --- Interesting / Read flags ---
    interesting = parser.add_argument_group("Interesting / Read flags")
    interesting.add_argument("--mark-interesting", type=int, nargs="+", metavar="ID",
                             help="Mark article(s) as interesting")
    interesting.add_argument("--unmark-interesting", type=int, nargs="+", metavar="ID",
                             help="Unmark article(s) as interesting")
    interesting.add_argument("--mark-read", type=int, nargs="+", metavar="ID",
                             help="Mark article(s) as read")
    interesting.add_argument("--unmark-read", type=int, nargs="+", metavar="ID",
                             help="Unmark article(s) as read")
    interesting.add_argument("--list-interesting", action="store_true",
                             help="List interesting articles")
    interesting.add_argument("--list-unread", action="store_true", help="List unread articles")

    # --- Excel export / import ---
    xlsx = parser.add_argument_group("Excel export / import")
    xlsx.add_argument("--export-xlsx", action="store_true", help="Export articles to Excel")
    xlsx.add_argument("--import-xlsx", type=str, metavar="PATH",
                      help="Import article flags from Excel file")
    xlsx.add_argument("--filter", type=str, choices=["all", "unread", "interesting"],
                      default="all", help="Filter for export")

    # --- Configuration ---
    config = parser.add_argument_group("Configuration")
    config.add_argument("--delay", type=float, nargs=2, metavar=("MIN", "MAX"),
                        help="Request delay range")
    config.add_argument("--timeout", type=int, help="Request timeout")
    config.add_argument("--output", "-o", default="data", help="Output directory")
    config.add_argument("--db", help="Path to database")
    config.add_argument("--temp-dir", default="../../../.temp",
                        help="Temp directory for batch files")
    config.add_argument("--verbose", "-v", action="store_true", help="Debug logging")
    config.add_argument("--json", action="store_true", help="Output as JSON")

    return parser


def _parse_ym(value: str) -> tuple[int, int]:
    parts = value.split("-")
    if len(parts) == 1:
        try:
            return (int(parts[0]), 0)
        except ValueError:
            raise ValueError(f"Invalid year: '{value}'.")
    if len(parts) != 2:
        raise ValueError(f"Invalid date format: '{value}'. Use YYYY or YYYY-MM.")
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        raise ValueError(f"Invalid date format: '{value}'. Use YYYY or YYYY-MM.")


def _parse_search_date(value: str, is_since: bool) -> tuple[int, int]:
    """Parse YYYY or YYYY-MM. For YYYY alone, default to YYYY-01 (since) or YYYY-12 (until)."""
    year, month = _parse_ym(value)
    if month == 0:
        month = 1 if is_since else 12
    if month < 1 or month > 12:
        raise ValueError(f"Invalid month: {month}")
    return year, month


def main(argv: list[str] | None = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")

    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(log_level)

    db_path = args.db or "data/radio.db"
    db = Database(db_path)

    request_cfg = RequestConfig()
    if args.delay:
        request_cfg.delay_min, request_cfg.delay_max = args.delay
    if args.timeout:
        request_cfg.timeout = args.timeout
    rate_limiter = AdaptiveRateLimiter(request_cfg)
    with_excerpt = not args.no_excerpt
    force = args.force
    force_format = "archive" if args.archive else ("arhiv" if args.arhiv else "")

    # --- Info commands ---
    if args.db_schema:
        schema = db.get_schema()
        if args.json:
            print(json.dumps(schema, indent=2, ensure_ascii=False))
            return 0
        for table in schema:
            print(f"\nTable: {table['table']}")
            print("-" * (len(table["table"]) + 8))
            for c in table["columns"]:
                pk = " PK" if c["pk"] else ""
                nn = " NOT NULL" if c["notnull"] else ""
                print(f"  {c['name']:20s} {c['type']}{pk}{nn}")
        return 0

    if args.db_summary:
        show_summary(db, args.json)
        return 0

    if args.latest:
        show_latest(db, args.latest, args.json)
        return 0

    if args.db_search:
        if not args.db_search.strip():
            logger.error("--db-search requires a non-empty keyword")
            return 1
        results = db.search_articles(args.db_search)
        if args.json:
            print(json.dumps(results, indent=2, ensure_ascii=False))
            return 0
        if not results:
            print(f"No articles found matching '{args.db_search}'.")
            return 0
        print(f"\nFound {len(results)} article(s) matching '{args.db_search}':")
        print()
        for i, r in enumerate(results, 1):
            ym = f"{r['year']:04d}-{r['month']:02d}"
            section = f" [{r['section']}]" if r.get("section") else ""
            print(f"{i}. {r['topic']} ({ym}){section}")
            if r.get("author"):
                print(f"   Author: {r['author']}  Page: {r.get('page', '?')}")
            if r.get("excerpt"):
                excerpt = r["excerpt"][:200] + "\u2026" if len(r["excerpt"]) > 200 else r["excerpt"]
                print(f"   {excerpt}")
            print()
        return 0

    # --- Subcommand dispatch ---
    if args.mode == "search":
        if args.command == "init":
            return _handle_search_init(args, db)
        elif args.command == "get-batch":
            return _handle_search_get_batch(args, db)
        elif args.command == "set-batch":
            return _handle_search_set_batch(args, db)
        elif args.command == "status":
            return _handle_search_status(args, db)
        elif args.command == "report":
            return _handle_search_report(args, db)
        logger.error("Unknown search command: %s", args.command)
        return 1

    if args.mode == "track":
        return _handle_track(args, db)

    if args.mode == "summarize":
        return _handle_summarize(args, db)

    # --- Interesting / Read / XLSX ---
    if (args.mark_interesting is not None or args.unmark_interesting is not None
            or args.mark_read is not None or args.unmark_read is not None
            or args.list_interesting or args.list_unread
            or args.export_xlsx or args.import_xlsx):
        return _handle_interesting(args, db)

    # --- Force re-fetch missing excerpts ---
    if args.force_excerpt:
        rows = db.get_months_without_excerpts()
        if not rows:
            print("No articles missing excerpts.")
            return 0
        session_id = db.create_session()
        logger.info("Session %d started (force-excerpt, %d months to process)", session_id, len(rows))
        total_excerpts = 0
        for row in rows:
            y, m = row["year"], row["month"]
            articles_to_fetch = db.get_articles_without_excerpt(y, m)
            if not articles_to_fetch:
                continue
            logger.info("Fetching excerpts for %04d-%02d (%d articles) ...", y, m, len(articles_to_fetch))

            worker = _make_excerpt_worker(y, m)
            results = fetch_all_parallel(articles_to_fetch, worker, request_cfg)

            batch_items = []
            for item, result, error in results:
                if error:
                    logger.warning("Failed excerpt for %s: %s", item["topic"], error)
                    continue
                if result.get("excerpt"):
                    batch_items.append((result["excerpt"], result["topic"], y, m))
                if result.get("pdf_url"):
                    db.update_pdf_url(result["topic"], y, m, result["pdf_url"])

            if batch_items:
                db.update_excerpts_batch(batch_items)
                total_excerpts += len(batch_items)

        db.finish_session(session_id, "completed")
        print(f"\nDone. Fetched {total_excerpts} missing excerpts across {len(rows)} months.")
        show_summary(db)
        return 0

    # --- Scraping logic ---
    session_id = db.create_session()
    logger.info("Session %d started", session_id)

    try:
        if args.year and args.month:
            result = scrape_month(
                db, args.year, args.month, session_id,
                request_cfg, rate_limiter,
                dry_run=args.dry_run,
                force=force,
                force_format=force_format,
            )
            if args.dry_run:
                print(f"\nDry run: {result} articles found on {args.year}-{args.month:02d}")
                db.finish_session(session_id, "dry_run")
            else:
                db.finish_session(session_id, "completed",
                                  total_months=1, total_found=max(0, result))
                if with_excerpt and result > 0:
                    _fetch_single_month_excerpts(db, args.year, args.month, request_cfg, dry_run=args.dry_run)
                show_summary(db)
            return 0 if result != -1 else 1

        if args.since or args.until:
            since_year, since_month = _parse_ym(args.since) if args.since else _parse_ym("1924-01")
            until_year, until_month = _parse_ym(args.until) if args.until else (datetime.now(timezone.utc).year, datetime.now(timezone.utc).month)

            total_found = 0
            months_done = 0
            y, m = since_year, since_month
            while (y > until_year) or (y == until_year and m >= until_month):
                if force or not db.is_month_scraped(y, m):
                    result = scrape_month(
                        db, y, m, session_id,
                        request_cfg, rate_limiter,
                        dry_run=args.dry_run,
                        force=force,
                        force_format=force_format,
                    )
                    if result > 0:
                        total_found += result
                    if result >= 0:
                        months_done += 1

                m -= 1
                if m == 0:
                    y -= 1
                    m = 12

            if args.dry_run:
                print(f"\nDry run: {total_found} articles in range {args.since} - {args.until}")
            else:
                db.finish_session(session_id, "completed",
                                  total_months=months_done, total_found=total_found)
                if with_excerpt and total_found > 0:
                    fetch_missing_excerpts(db, session_id, request_cfg, dry_run=args.dry_run)
                show_summary(db)
            return 0

        # Default: auto-scan (parallel)
        now = datetime.now(timezone.utc)
        start_year = args.year or now.year
        start_month = args.month or now.month

        total = auto_scan_parallel(
            db, session_id, request_cfg, rate_limiter,
            start_year, start_month,
            max_404=args.max_404,
            dry_run=args.dry_run,
            force=force,
            force_format=force_format,
        )
        if args.dry_run:
            return 0
        db.finish_session(session_id, "completed", total_found=total)
        if with_excerpt and total > 0:
            fetch_missing_excerpts(db, session_id, request_cfg, dry_run=args.dry_run)
        show_summary(db)
        return 0

    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        db.finish_session(session_id, "interrupted")
        return 130
    except Exception as e:
        logger.exception("Fatal error: %s", e)
        db.finish_session(session_id, "failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())