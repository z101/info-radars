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
    compute_rubric_hash,
)
from analyzer.report import generate_report, generate_report_text
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
        logger.warning("Failed to fetch %s: %s", url, e)
        if not dry_run:
            db.mark_month_error(year, month, session_id, str(e))
        return -1

    articles = parse_content_page(html, url=url, year=year)
    if not articles:
        logger.info("No articles found on %s", url)
        if not dry_run:
            db.mark_month_done(year, month, session_id, 0)
        return 0

    logger.info("Found %d articles in %s", len(articles), url)

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
            ts = datetime.now().strftime("%H:%M:%S")
            if result == -1:
                consecutive_404 += 1
                consecutive_empty = 0
                if not dry_run:
                    db.mark_month_404(by, bm, session_id, consecutive_404)
                logger.info("Month %04d-%02d: 404 (%d consecutive)", by, bm, consecutive_404)
                print(f"[{ts}] \u2717 {by:04d}-{bm:02d} \u2014 404 ({consecutive_404}/{max_404})")
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
                logger.info("Month %04d-%02d: empty", by, bm)
            else:
                total_found += result
                total_months += 1
                consecutive_404 = 0
                consecutive_empty = 0
                logger.info("Month %04d-%02d: %d articles", by, bm, result)
                print(f"[{ts}] \u2713 {by:04d}-{bm:02d} \u2014 {result} articles")

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
        print("  All excerpts already fetched.")
        return 0

    total_articles = sum(
        len(db.get_articles_without_excerpt(r["year"], r["month"])) for r in rows
    )
    if total_articles == 0:
        print("  All excerpts already fetched.")
        return 0

    total_months = len(rows)
    fetched = 0
    errors = 0
    start_time = time.time()

    for idx, row in enumerate(rows, 1):
        y, m = row["year"], row["month"]
        articles_to_fetch = db.get_articles_without_excerpt(y, m)
        if not articles_to_fetch:
            continue

        worker = _make_excerpt_worker(y, m)
        results = fetch_all_parallel(articles_to_fetch, worker, request_cfg)

        month_ok = 0
        month_err = 0
        batch_items = []
        for item, result, error in results:
            if error:
                logger.warning("Failed excerpt for %s: %s", item["topic"], error)
                month_err += 1
                continue
            if result.get("excerpt"):
                batch_items.append((result["excerpt"], result["topic"], y, m))
                month_ok += 1
            if result.get("pdf_url"):
                db.update_pdf_url(result["topic"], y, m, result["pdf_url"])

        if batch_items:
            updated = db.update_excerpts_batch(batch_items)
            fetched += updated

        fetched += month_ok
        errors += month_err

        elapsed = time.time() - start_time
        pct = idx / total_months * 100
        rate = fetched / elapsed if elapsed > 0 else 0
        eta = (total_articles - fetched) / rate if rate > 0 else 0
        bar_len = 20
        filled = int(bar_len * idx / total_months)
        bar = "\u2588" * filled + "\u2591" * (bar_len - filled)
        print(
            f"\r  {bar}  {pct:3.0f}%  |  Month {idx}/{total_months} ({y:04d}-{m:02d})  "
            f"|  {fetched}/{total_articles} excerpts  |  eta {eta:.0f}s  ",
            end="", flush=True,
        )

    print()
    if errors:
        logger.info("Excerpt pass complete: %d fetched, %d errors across %d months", fetched, errors, total_months)
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
        print(f"  Years:    {summary['year_range'][0]} \u2014 {summary['year_range'][1]}")
    if summary.get("earliest"):
        print(f"  Range:    {summary['earliest']} \u2014 {summary['latest']}")
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


def _resolve_hashes(args) -> tuple[str, str, str, str, dict]:
    query_name, query_text = _load_query_file(args.query_file)
    query_hash = compute_query_hash(query_text)
    cfg = DEFAULT_ANALYZE_CONFIG
    rubric_hash = compute_rubric_hash(cfg["criteria"])
    return query_name, query_text, query_hash, rubric_hash, cfg


def _save_search_results(
    db: Database,
    results: list,
    args,
    query_hash: str,
    rubric_hash: str,
    query_name: str,
    query_text: str,
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
                article_id, query_hash, rubric_hash, content_hash,
                args.stage, str(item["error"]), query_name, query_text,
            )
            errors += 1
            continue

        if args.stage == "filter":
            keep = bool(item.get("keep", True))
            reason = item.get("reason", "")
            db.save_search_filter(
                article_id, query_hash, query_name, query_text,
                rubric_hash, content_hash, keep, reason,
            )
            saved += 1
        elif args.stage == "rerank":
            scores = item.get("scores", {})
            total = item.get("total", sum(scores.values()) if scores else 0)
            comment = item.get("comment", "")
            ok = db.save_search_score(
                article_id, query_hash, rubric_hash,
                scores, total, comment,
            )
            if ok:
                saved += 1
            else:
                logger.warning("No active filter row for article id=%s; score skipped", article_id)
                errors += 1

    logger.info("Saved %d result(s), %d error(s) for stage=%s", saved, errors, args.stage)
    if not args.json:
        print(f"Saved {saved} result(s), {errors} error(s) for stage={args.stage}")
    return 0


def _handle_search_pipeline(args, db: Database) -> int:
    if not args.query_file:
        logger.error("--query-file is required for search commands")
        return 1

    try:
        query_name, query_text, query_hash, rubric_hash, cfg = _resolve_hashes(args)
    except (FileNotFoundError, ValueError) as e:
        logger.error("%s", e)
        return 1

    max_retries = 3

    if args.search_skip_filter:
        candidates = db.get_search_candidates(query_hash, rubric_hash, "filter", max_retries)
        for c in candidates:
            db.save_search_filter(
                c["id"], query_hash, query_name, query_text,
                rubric_hash, c["content_hash"], True, "auto-kept (filter disabled)",
            )
        msg = f"Marked {len(candidates)} article(s) as kept (filter disabled)."
        logger.info(msg)
        if not args.json:
            print(msg)
        return 0

    if args.search_status:
        status = db.get_search_status(query_hash, rubric_hash)
        if args.json:
            print(json.dumps(status, indent=2, ensure_ascii=False))
        else:
            total = status["total_articles"]
            print(f"\nAnalysis status for query '{query_name}':")
            print(f"  Total articles in DB: {total}")
            for s, cnt in sorted(status["by_status"].items()):
                print(f"  {s:12s}: {cnt}")
        return 0

    if args.search_candidates:
        if not args.stage:
            logger.error("--stage is required for --search-candidates")
            return 1
        batch_size = cfg.get("primary_filter", {}).get("batch_size", 100)
        if args.stage == "rerank":
            batch_size = cfg.get("batch_size", 20)
        if args.batch is not None:
            candidates = db.get_search_candidates_batch(
                query_hash, rubric_hash, args.stage, args.batch, batch_size, max_retries,
            )
        else:
            candidates = db.get_search_candidates(query_hash, rubric_hash, args.stage, max_retries)
        print(json.dumps(candidates, indent=2, ensure_ascii=False, default=str))
        return 0

    if args.search_save_stdin:
        if not args.stage:
            logger.error("--stage is required for --search-save-stdin")
            return 1
        try:
            results = json.loads(sys.stdin.read())
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON from stdin: %s", e)
            return 1
        if not isinstance(results, list):
            logger.error("Expected a JSON array from stdin")
            return 1
        return _save_search_results(db, results, args, query_hash, rubric_hash, query_name, query_text)

    if args.search_save:
        if not args.stage:
            logger.error("--stage is required for --search-save")
            return 1
        save_path = Path(args.search_save)
        if not save_path.exists():
            logger.error("File not found: %s", args.search_save)
            return 1
        try:
            results = json.loads(save_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in %s: %s", args.search_save, e)
            return 1
        if not isinstance(results, list):
            logger.error("Expected a JSON array in %s", args.search_save)
            return 1
        return _save_search_results(db, results, args, query_hash, rubric_hash, query_name, query_text)

    if args.search_report:
        csv_path = generate_report(
            db, query_name, query_hash, rubric_hash,
            min_total=args.min_total or 0, top=args.top,
        )
        if csv_path is None:
            print(f"No scored results yet for query '{query_name}'.")
            print("Run the search pipeline first (filter + rerank stages).")
        return 0

    return 0


def _handle_search(args, db: Database) -> int:
    query_text = args.search.strip()
    if not query_text:
        logger.error("--search requires non-empty text")
        return 1

    query_hash = compute_query_hash(query_text)
    query_name = f"search_{query_hash[:12]}"
    rubric_hash = compute_rubric_hash(DEFAULT_ANALYZE_CONFIG["criteria"])

    if args.query_file:
        query_name, query_text = _load_query_file(args.query_file)
        query_hash = compute_query_hash(query_text)

    status = db.get_search_status(query_hash, rubric_hash)
    total = status["total_articles"]
    scored = status["by_status"].get("scored", 0)
    pending = total - scored

    if pending <= 0:
        text = generate_report_text(
            db, query_name, query_hash, rubric_hash,
            min_total=args.min_total or 0, top=args.top or 20,
        )
        csv_path = generate_report(
            db, query_name, query_hash, rubric_hash,
            min_total=args.min_total or 0, top=args.top,
        )
        if text:
            print(text)
        else:
            print("No scored results match the criteria.")
        return 0

    cfg = DEFAULT_ANALYZE_CONFIG
    batch_size = cfg["primary_filter"]["batch_size"]
    parallel = cfg["parallel_agents"]

    print(f"\n=== SEARCH REQUIRED: '{query_name}' ===")
    print(f"Uncached articles: {total - scored} (total: {total}, scored: {scored})")
    print()
    print(f"Stage 1 \u2014 filter (triage):")
    filter_batches = (pending + batch_size - 1) // batch_size
    print(f"  Batch size: {batch_size}")
    print(f"  Batches: {filter_batches}")
    print(f"  Parallel agents: {parallel}")
    print()
    print(f"  Commands for batch 0:")
    print(f"    --search-candidates --stage filter --batch 0 --json")
    print()
    print(f"  After subagent evaluation:")
    print(f"    --search-save <result_file> --stage filter")
    print()
    print(f"  Repeat for batches 1..{filter_batches - 1}.")
    print()
    if scored > 0:
        print(f"  Note: {scored} already scored articles will be in the report.")
    print()
    print(f"After all filter batches, re-run the same command for rerank stage.")
    print()
    print(f"Re-run this command after all stages complete to get the report.")
    return 0


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
            "  %(prog)s                                      # Auto-scan from current month\n"
            "  %(prog)s --year 2026 --month 4                 # Single month\n"
            "  %(prog)s --since 2025-01 --until 2026-04       # Range\n"
            "  %(prog)s --db-summary                          # DB status\n"
            "  %(prog)s --dry-run --year 2026 --month 4       # Validate without saving\n"
            "  %(prog)s --no-excerpt                          # Skip annotations\n"
            "  %(prog)s --year 2026 --month 4 --force         # Re-scrape month\n"
            "  %(prog)s --search \"ESP32\" --top 10             # Semantic search\n"
            "  %(prog)s --export-xlsx                         # Export to Excel\n"
            "  %(prog)s --mark-interesting 5 12               # Mark articles as interesting\n"
        ),
    )

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

    info = parser.add_argument_group("Information options")
    info.add_argument("--db-summary", action="store_true", help="Show database summary")
    info.add_argument("--db-schema", action="store_true", help="Show database schema")
    info.add_argument("--latest", type=int, metavar="N", help="Show N most recent articles")
    info.add_argument("--db-search", type=str, metavar="KEYWORD", help="Search articles by keyword")

    analysis = parser.add_argument_group("Search pipeline")
    analysis.add_argument("--query-file", type=str, metavar="PATH", help="Path to a query file")
    analysis.add_argument("--stage", type=str, choices=["filter", "rerank"], help="Pipeline stage")
    analysis.add_argument("--search-candidates", action="store_true", help="List search candidates")
    analysis.add_argument("--batch", type=int, default=None, metavar="N", help="Batch number for candidates")
    analysis.add_argument("--search-save", type=str, metavar="PATH", help="Save search results from JSON file")
    analysis.add_argument("--search-save-stdin", action="store_true", help="Save search results from stdin")
    analysis.add_argument("--search-report", action="store_true", help="Print ranked search report")
    analysis.add_argument("--search-status", action="store_true", help="Show search progress")
    analysis.add_argument("--search-skip-filter", action="store_true", help="Skip filter stage, mark all as kept")
    analysis.add_argument("--search", type=str, metavar="TEXT", help="Ad-hoc search query")
    analysis.add_argument("--top", type=int, metavar="N", help="Limit report to top N")
    analysis.add_argument("--min-total", type=int, default=0, metavar="N", help="Minimum total score")

    interesting = parser.add_argument_group("Interesting / Read flags")
    interesting.add_argument("--mark-interesting", type=int, nargs="+", metavar="ID", help="Mark article(s) as interesting")
    interesting.add_argument("--unmark-interesting", type=int, nargs="+", metavar="ID", help="Unmark article(s) as interesting")
    interesting.add_argument("--mark-read", type=int, nargs="+", metavar="ID", help="Mark article(s) as read")
    interesting.add_argument("--unmark-read", type=int, nargs="+", metavar="ID", help="Unmark article(s) as read")
    interesting.add_argument("--list-interesting", action="store_true", help="List interesting articles")
    interesting.add_argument("--list-unread", action="store_true", help="List unread articles")

    xlsx = parser.add_argument_group("Excel export / import")
    xlsx.add_argument("--export-xlsx", action="store_true", help="Export articles to Excel")
    xlsx.add_argument("--import-xlsx", type=str, metavar="PATH", help="Import article flags from Excel file")
    xlsx.add_argument("--filter", type=str, choices=["all", "unread", "interesting"], default="all", help="Filter for export")

    config = parser.add_argument_group("Configuration")
    config.add_argument("--delay", type=float, nargs=2, metavar=("MIN", "MAX"), help="Request delay range")
    config.add_argument("--timeout", type=int, help="Request timeout")
    config.add_argument("--output", "-o", default="data", help="Output directory")
    config.add_argument("--db", help="Path to database")
    config.add_argument("--verbose", "-v", action="store_true", help="Debug logging")
    config.add_argument("--json", action="store_true", help="Output as JSON")

    return parser


def _parse_ym(value: str) -> tuple[int, int]:
    parts = value.split("-")
    if len(parts) != 2:
        raise ValueError(f"Invalid date format: '{value}'. Use YYYY-MM.")
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        raise ValueError(f"Invalid date format: '{value}'. Use YYYY-MM.")


def main(argv: list[str] | None = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

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

    # --- Search pipeline ---
    if args.search:
        return _handle_search(args, db)

    if (args.search_candidates or args.search_save or args.search_save_stdin
            or args.search_report or args.search_status or args.search_skip_filter):
        return _handle_search_pipeline(args, db)

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
                print(f"\nDry run: {total_found} articles in range {args.since} \u2014 {args.until}")
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