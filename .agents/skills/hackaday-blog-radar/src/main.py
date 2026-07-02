import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from html2text import HTML2Text

# Ensure src/ is on sys.path for sibling package imports
_src = Path(__file__).parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from analyzer.config import DEFAULT_ANALYZE_CONFIG
from analyzer.hashes import (
    compute_content_hash,
    compute_params_hash,
    compute_query_hash,
    compute_rubric_hash,
)
from analyzer.prompts import format_interest_articles
from analyzer.report import generate_report, generate_report_text, generate_digest_report
from analyzer.trends import run_trend_analysis, save_trend_interpretation
from database import Database
from scraper.exporter import export_json, format_info
from scraper.fetcher import (
    AdaptiveRateLimiter,
    RequestConfig,
    fetch_all_parallel,
    fetch_available_categories,
    fetch_html,
)
from scraper.logging import setup_logging
from scraper.parser import (
    get_first_page_info,
    parse_archive_page,
    parse_article_page,
    validate_articles,
)
from xlsx_exporter import export_to_xlsx, import_from_xlsx

logger = logging.getLogger(__name__)


def _make_markdown_converter() -> HTML2Text:
    h = HTML2Text()
    h.body_width = 0
    h.ignore_links = False
    h.ignore_images = False
    h.ignore_emphasis = False
    h.protect_links = True
    h.unicode_snob = True
    h.skip_internal_links = True
    h.inline_links = True
    return h


def _clean_content(html: str) -> str:
    converter = _make_markdown_converter()
    return converter.handle(html).strip()


def _fetch_article_full(
    url: str,
    request_cfg: RequestConfig,
    rate_limiter: AdaptiveRateLimiter,
) -> dict:
    html = fetch_html(url, request_cfg, rate_limiter)
    parsed = parse_article_page(html)
    content_md = None
    if parsed["content_html"]:
        content_md = _clean_content(parsed["content_html"])
    return {
        "url": url,
        "html": html,
        "author": parsed["author"],
        "content_md": content_md,
        "comments": parsed["comments"],
        "has_comments": parsed["has_comments_section"],
    }


def _scrape_article_worker(
    article_row: dict,
    request_cfg: RequestConfig,
    rate_limiter: AdaptiveRateLimiter,
) -> dict:
    url = article_row["url"]
    try:
        result = _fetch_article_full(url, request_cfg, rate_limiter)
        return {"id": article_row["id"], "url": url, "success": True, **result}
    except Exception as e:
        logger.warning("Failed to fetch %s: %s", url, e)
        return {"id": article_row["id"], "url": url, "success": False, "error": str(e)}


def scrape_archive_pages(
    db: Database,
    category: str,
    session_id: int,
    request_cfg: RequestConfig,
    dry_run: bool = False,
    max_pages: int | None = None,
    until: str | None = None,
) -> int:
    from bs4 import BeautifulSoup
    from tqdm import tqdm

    rate_limiter = AdaptiveRateLimiter(request_cfg)
    base_url = f"https://hackaday.com/category/{category}"

    logger.info("Fetching first page of '%s'...", category)
    html = fetch_html(base_url, request_cfg, rate_limiter)

    soup = BeautifulSoup(html, "html.parser")
    total, per_page = get_first_page_info(soup)
    logger.info("Counter says: %d total articles, %d per page", total, per_page)

    articles = parse_archive_page(html)
    errors = validate_articles(articles)
    if errors:
        for e in errors:
            logger.warning("Validation: %s", e)
        if dry_run:
            logger.info("DRY RUN \u2014 found %d articles with %d error(s)", len(articles), len(errors))

    now = datetime.now(timezone.utc).isoformat()
    for a in articles:
        db.upsert_article(category, a["title"], a["url"], session_id, now, a["date"], a["excerpt"], a["tags"])

    db.mark_page_done(category, 1, session_id, len(articles))

    if until and all(a["date"] < until for a in articles):
        logger.info("--until %s: page 1 already past cutoff, nothing to scrape", until)
        db.finish_session(session_id, "completed", total_pages=1, total_found=0)
        return 0

    if dry_run:
        logger.info("DRY RUN \u2014 first page: %d articles", len(articles))
        for a in articles[:3]:
            logger.info("  \u2022 %s (%s)", a["title"], a["date"])
        return len(articles)

    if max_pages is not None and max_pages <= 1:
        logger.info("Max pages reached (1): %d articles saved", len(articles))
        db.finish_session(session_id, "running", total_pages=1, total_found=len(articles))
        return len(articles)

    total_pages = (total + per_page - 1) // per_page
    done_pages = db.get_done_pages(category) if not dry_run else set()
    error_pages = db.get_error_pages(category, request_cfg.max_retries) if not dry_run else set()
    pages_to_scrape = sorted(
        p for p in range(2, total_pages + 1)
        if p not in done_pages or p in error_pages
    )

    if max_pages is not None:
        pages_to_scrape = pages_to_scrape[:max_pages - 1]
        logger.info("Max pages: %d, scraping pages: %s", max_pages, pages_to_scrape if pages_to_scrape else "none")

    logger.info("Pages: %d total, %d done, %d remaining", total_pages, len(done_pages), len(pages_to_scrape))

    for page_num in tqdm(pages_to_scrape, desc=f"Scraping {category} archive", unit="page"):
        url = f"{base_url}/page/{page_num}/"
        try:
            page_html = fetch_html(url, request_cfg, rate_limiter)
            soup = BeautifulSoup(page_html, "html.parser")
            page_articles = parse_archive_page(page_html)

            if not page_articles:
                logger.info("Page %d: empty, stopping", page_num)
                break

            if until and all(a["date"] < until for a in page_articles):
                logger.info("--until %s: all articles older than cutoff, stopping at page %d", until, page_num)
                break

            page_errors = validate_articles(page_articles)
            for e in page_errors:
                logger.warning("Page %d validation: %s", page_num, e)

            for a in page_articles:
                db.upsert_article(category, a["title"], a["url"], session_id, now, a["date"], a["excerpt"], a["tags"])

            db.mark_page_done(category, page_num, session_id, len(page_articles))

        except Exception as e:
            logger.error("Page %d: %s", page_num, e)
            db.mark_page_error(category, page_num, session_id, str(e))

    total_found = db._fetchone(
        "SELECT COUNT(*) as cnt FROM articles WHERE category = ?", (category,)
    )["cnt"]
    db.finish_session(session_id, "running", total_pages, total_found)
    logger.info("Phase 1 complete: %d articles collected", total_found)
    return total_found


def scrape_full_articles(
    db: Database,
    category: str,
    session_id: int,
    request_cfg: RequestConfig,
    since: str | None = None,
    skip_comments: bool = False,
):
    from tqdm import tqdm

    articles = db.get_articles_for_full_text(category, since)
    if not articles:
        logger.info("No articles waiting for full text download.")
        return

    logger.info("Fetching full text for %d articles...", len(articles))

    pbar = tqdm(total=len(articles), desc="Fetching full articles", unit="article")

    def progress(n=1):
        pbar.update(n)

    results = fetch_all_parallel(
        articles,
        lambda row, cfg, rl: _scrape_article_worker(row, cfg, rl),
        request_cfg,
        progress_callback=progress,
    )

    full_count = 0
    error_count = 0
    for item, result, error in results:
        if error is not None:
            db.mark_article_error(item["id"])
            error_count += 1
        else:
            db.update_article_full_text(
                result["id"],
                result.get("html", ""),
                result.get("content_md", ""),
                session_id,
                author=result.get("author"),
            )
            if result.get("comments") and not skip_comments:
                for c in result["comments"]:
                    db.insert_comment(result["id"], result["url"], c["author"], c["date"], c["content"])
            full_count += 1

    pbar.close()
    logger.info("Phase 2 complete: %d full texts fetched, %d errors", full_count, error_count)


def show_info(db: Database, category: str | None = None):
    print(format_info(db, category))


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
            "SELECT content_md, title, excerpt FROM articles WHERE id = ?", (article_id,)
        )
        if not row:
            logger.warning("Article id=%s not found in DB", article_id)
            continue

        content_hash = compute_content_hash(row["content_md"], row["title"] or "", row["excerpt"] or "")

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
        if not args.category:
            logger.error("--category is required for --search-skip-filter")
            return 1
        candidates = db.get_search_candidates(
            args.category, query_hash, rubric_hash, "filter", max_retries
        )
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
        if not args.category:
            logger.error("--category is required for --search-status")
            return 1
        status = db.get_search_status(args.category, query_hash, rubric_hash)
        if args.json:
            print(json.dumps(status, indent=2, ensure_ascii=False))
        else:
            total = status["total_articles"]
            print(f"\nAnalysis status for '{args.category}' / query '{query_name}':")
            print(f"  Total articles in DB: {total}")
            for s, cnt in sorted(status["by_status"].items()):
                print(f"  {s:12s}: {cnt}")
        return 0

    if args.search_candidates:
        if not args.category:
            logger.error("--category is required for --search-candidates")
            return 1
        if not args.stage:
            logger.error("--stage is required for --search-candidates")
            return 1
        batch_size = DEFAULT_ANALYZE_CONFIG.get("primary_filter", {}).get("batch_size", 100)
        if args.stage == "rerank":
            batch_size = DEFAULT_ANALYZE_CONFIG.get("batch_size", 20)
        if args.batch is not None:
            candidates = db.get_search_candidates_batch(
                args.category, query_hash, rubric_hash, args.stage,
                args.batch, batch_size, max_retries,
            )
        else:
            candidates = db.get_search_candidates(
                args.category, query_hash, rubric_hash, args.stage, max_retries
            )
        if args.stage == "rerank":
            for c in candidates:
                comments = db.get_search_comments(c["id"])
                c["comments"] = comments
        print(json.dumps(candidates, indent=2, ensure_ascii=False, default=str))
        return 0

    if args.search_save_stdin:
        if not args.category:
            logger.error("--category is required for --search-save-stdin")
            return 1
        if not args.stage:
            logger.error("--stage is required for --search-save-stdin")
            return 1
        if not args.query_file:
            logger.error("--query-file is required for --search-save-stdin")
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
        if not args.category:
            logger.error("--category is required for --search-save")
            return 1
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
        if not args.category:
            logger.error("--category is required for --search-report")
            return 1

        csv_path = generate_report(
            db, args.category, query_name, query_hash, rubric_hash,
            min_total=args.min_total or 0, top=args.top,
        )
        if csv_path is None:
            print(f"No scored results yet for query '{query_name}' in category '{args.category}'.")
            print("Run the search pipeline first (filter + rerank stages).")
        return 0

    return 0


def _handle_search(args, db: Database) -> int:
    if not args.category:
        logger.error("--category is required for --search")
        return 1

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

    status = db.get_search_status(args.category, query_hash, rubric_hash)
    total = status["total_articles"]
    scored = status["by_status"].get("scored", 0)
    pending = total - scored

    if pending <= 0:
        text = generate_report_text(
            db, args.category, query_name, query_hash, rubric_hash,
            min_total=args.min_total or 0, top=args.top or 20,
        )
        csv_path = generate_report(
            db, args.category, query_name, query_hash, rubric_hash,
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
    print(f"Category: {args.category}")
    print(f"Uncached articles: {total - scored} (total: {total}, scored: {scored})")
    print(f"")
    print(f"Stage 1 — filter (triage):")
    filter_batches = (pending + batch_size - 1) // batch_size
    print(f"  Batch size: {batch_size}")
    print(f"  Batches: {filter_batches}")
    print(f"  Parallel agents: {parallel}")
    print(f"")
    print(f"  Commands for batch 0:")
    print(f"    --search-candidates --stage filter -c {args.category} --batch 0 --json")
    print(f"")
    print(f"  After subagent evaluation:")
    print(f"    --search-save <result_file> --stage filter")
    print(f"")
    print(f"  Repeat for batches 1..{filter_batches - 1}.")
    print(f"")
    if scored > 0:
        print(f"  Note: {scored} already scored articles will be in the report.")
    print(f"")
    print(f"After all filter batches, re-run the same command for rerank stage.")
    print(f"")
    print(f"Re-run this command after all stages complete to get the report.")
    return 0


def _handle_trends(args, db: Database) -> int:
    if not args.category:
        logger.error("--category is required for --trends")
        return 1

    period_start = args.since or "2000-01-01"
    period_end = args.until or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    result = run_trend_analysis(db, args.category, period_start, period_end, args.trend_keyword)

    if result["status"] == "needs_llm":
        print(f"\n=== TREND ANALYSIS: {args.category} ===")
        print(f"Period: {period_start} — {period_end}")
        print(f"\nAggregated data ready. {result['sql_data']['aggregates']['total_articles']} articles found.")
        print(f"\nFormatted data for LLM interpretation:\n")
        print(result["formatted"])
        print(f"\nParams hash: {result['params_hash']}")
        print("\nTo save LLM interpretation:")
        print(f"  --save-trend-interpretation <hash> \"your interpretation text\"")
    else:
        print(result["interpretation"])

    return 0


def _handle_digest(args, db: Database) -> int:
    if not args.category:
        logger.error("--category is required for --digest")
        return 1

    interests_dir = args.interests_dir or Path("../../../interests/hackaday-blog-radar")
    interests_path = Path(interests_dir)

    if not interests_path.exists():
        logger.error("Interests directory not found: %s", interests_path)
        return 1

    interest_files = sorted(interests_path.glob("*.md"))
    if not interest_files:
        logger.error("No interest files (*.md) found in %s", interests_path)
        return 1

    period_start = args.since or "2000-01-01"
    period_end = args.until or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rubric_hash = compute_rubric_hash(DEFAULT_ANALYZE_CONFIG["criteria"])

    print(f"\n=== DIGEST: {args.category} ===")
    print(f"Period: {period_start} — {period_end}")
    print(f"Interest files: {[f.stem for f in interest_files]}")
    print(f"")

    for f in interest_files:
        query_name = f.stem
        query_text = f.read_text(encoding="utf-8").strip()
        query_hash = compute_query_hash(query_text)

        status = db.get_search_status(args.category, query_hash, rubric_hash)
        scored = status["by_status"].get("scored", 0)

        print(f"[{query_name}] scored: {scored}/{status['total_articles']}")

        if scored > 0:
            report_path = generate_digest_report(
                db, args.category, query_name, query_text,
                query_hash, rubric_hash,
                period_start, period_end,
                top=args.top or 5,
            )
            print(f"  Digest saved: {report_path}")
        else:
            print(f"  No scored results. Run search for this query first.")
        print()

    return 0


def _handle_summarize(args, db: Database) -> int:
    if not args.category:
        logger.error("--category is required for summarization")
        return 1

    if args.summarize_status:
        status = db.get_summary_status(args.category)
        print(f"\nSummarization status for '{args.category}':")
        print(f"  Total articles:   {status['total_articles']}")
        print(f"  With full text:   {status['with_full_text']}")
        print(f"  With summary:     {status['with_summary']}")
        print(f"  Pending:          {status['pending']}")
        return 0

    if args.summarize_candidates:
        batch_size = args.batch_size or 100
        batch = args.batch or 0
        articles = db.get_articles_for_summary(args.category, batch, batch_size)
        if not articles:
            print("No articles pending summarization in this batch.")
            return 0
        print(json.dumps(articles, indent=2, ensure_ascii=False, default=str))
        return 0

    if args.summarize_save:
        save_path = Path(args.summarize_save)
        if not save_path.exists():
            logger.error("File not found: %s", args.summarize_save)
            return 1
        try:
            results = json.loads(save_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in %s: %s", args.summarize_save, e)
            return 1
        if not isinstance(results, list):
            logger.error("Expected a JSON array in %s", args.summarize_save)
            return 1
        saved = 0
        for item in results:
            article_id = item.get("id")
            summary = item.get("summary_ru", "")
            if article_id is None:
                logger.warning("Skipping item without 'id'")
                continue
            db.save_summary(article_id, summary)
            saved += 1
        logger.info("Saved summaries for %d article(s)", saved)
        if not args.json:
            print(f"Saved summaries for {saved} article(s)")
        return 0

    return 0


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
        if not args.category:
            logger.error("--category is required for --list-interesting")
            return 1
        articles = db.get_interesting_articles(args.category)
        if not articles:
            print(f"No interesting articles for '{args.category}'.")
            return 0
        for a in articles:
            tags = ", ".join(a["tags"]) if a["tags"] else "—"
            read_mark = "[R]" if a["is_read"] else "   "
            print(f"[{a['id']}] [I]{read_mark} {a['title']} ({a['date']})")
            print(f"       {a['url']}")
            if a["summary_ru"]:
                print(f"       {a['summary_ru'][:200]}")
            print()
        return 0

    if args.list_unread:
        if not args.category:
            logger.error("--category is required for --list-unread")
            return 1
        articles = db.get_unread_articles(args.category)
        if not articles:
            print(f"All articles read for '{args.category}'.")
            return 0
        for a in articles:
            tags = ", ".join(a["tags"]) if a["tags"] else "—"
            interesting_mark = "[I]" if a["is_interesting"] else "   "
            print(f"[{a['id']}] {interesting_mark}[R] {a['title']} ({a['date']})")
            print(f"       {a['url']}")
            if a["summary_ru"]:
                print(f"       {a['summary_ru'][:200]}")
            print()
        return 0

    if args.generate_query_from_interesting:
        if not args.category:
            logger.error("--category is required for --generate-query-from-interesting")
            return 1
        articles = db.get_interesting_articles(args.category)
        if not articles:
            print(f"No interesting articles for '{args.category}'. Mark some first.")
            return 1

        fmt_articles = "\n\n".join(
            f"Title: {a['title']}\nDate: {a['date']}\nTags: {', '.join(a['tags'])}\n"
            f"Summary: {a['summary_ru'] or '—'}\nURL: {a['url']}"
            for a in articles
        )

        prompt = DEFAULT_ANALYZE_CONFIG["prompt_interesting_to_query"].format(
            articles=fmt_articles,
        )
        print("=== Articles for query generation ===")
        print(f"Found {len(articles)} interesting articles.")
        print(f"\nPrompt for subagent:\n{prompt}\n")
        print("(Subagent call goes here — returns query text)")
        print("Save result to interests/hackaday-blog-radar/<name>.md")
        return 0

    if args.export_xlsx:
        if not args.category:
            logger.error("--category is required for --export-xlsx")
            return 1
        filter_mode = args.filter or "all"
        articles = db.get_articles_for_export(args.category, filter_mode)
        if not articles:
            print(f"No articles to export for '{args.category}' (filter={filter_mode}).")
            return 0
        today = datetime.now().strftime("%Y-%m-%d")
        reports_dir = Path("../../../reports/hackaday-blog-radar")
        reports_dir.mkdir(parents=True, exist_ok=True)
        output_path = reports_dir / f"{args.category}_articles_{today}.xlsx"
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


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape and analyze Hackaday articles by category",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s --category led-hacks              # Resume mode (default)\n"
            "  %(prog)s --category led-hacks --reset      # Scrape from scratch\n"
            "  %(prog)s --category led-hacks --full-text  # Also download full articles\n"
            "  %(prog)s --category led-hacks --since 2025-06-01  # Only articles since date\n"
            "  %(prog)s --category led-hacks --until 2025-01-01  # Scrape newest until cutoff\n"
            "  %(prog)s --list-categories                 # List available categories\n"
            "  %(prog)s --info                            # Show database status\n"
            "  %(prog)s --db-schema                       # Show DB schema\n"
            "  %(prog)s --db-summary -c led-hacks         # Show DB summary for category\n"
            "  %(prog)s --search \"LED matrix\" -c led-hacks  # Ad-hoc search\n"
            "  %(prog)s --trends -c led-hacks --since 2025-01-01       # Trend analysis\n"
            "  %(prog)s --digest -c led-hacks --since 2025-01-01       # Interest digest\n"
            "  %(prog)s --mark-interesting 42 57 -c led-hacks  # Mark articles\n"
            "  %(prog)s --list-interesting -c led-hacks         # Show interesting\n"
            "  %(prog)s --mark-read 42 -c led-hacks            # Mark as read\n"
            "  %(prog)s --list-unread -c led-hacks             # Show unread\n"
            "  %(prog)s --export-xlsx -c led-hacks --filter unread  # Export to Excel\n"
            "  %(prog)s --import-xlsx reports/hackaday-blog-radar/led-hacks_articles_2026-07-03.xlsx  # Import flags\n"
        ),
    )

    scrape = parser.add_argument_group("Scraping options")
    scrape.add_argument("--category", "-c", help="Category slug to scrape (e.g. led-hacks, 3d-printing-hacks).")
    scrape.add_argument("--full-text", "-f", action="store_true", help="Also download full article text in phase 2")
    scrape.add_argument("--full-text-only", action="store_true", help="Skip phase 1, only download full texts")
    scrape.add_argument("--metadata-only", action="store_true", help="Skip phase 2, only scrape metadata")
    scrape.add_argument("--since", type=str, metavar="YYYY-MM-DD", help="Only process articles newer than this date")
    scrape.add_argument("--until", type=str, metavar="YYYY-MM-DD", help="Scrape from newest until this cutoff date")
    scrape.add_argument("--reset", action="store_true", help="Delete all data for this category before scraping")
    scrape.add_argument("--skip-comments", action="store_true", help="Skip parsing comments")
    scrape.add_argument("--max-pages", type=int, metavar="N", help="Stop after N archive pages")
    scrape.add_argument("--dry-run", action="store_true", help="Validate first page only \u2014 no save")

    info = parser.add_argument_group("Information options")
    info.add_argument("--info", action="store_true", help="Show scrape status")
    info.add_argument("--list-categories", action="store_true", help="List available categories")
    info.add_argument("--latest", type=int, metavar="N", help="Show N most recent articles")
    info.add_argument("--since-date", action="store_true", help="Print latest article date")

    export = parser.add_argument_group("Export options")
    export.add_argument("--export-json", action="store_true", help="Export articles to JSON")

    db_group = parser.add_argument_group("Database query options")
    db_group.add_argument("--db-schema", action="store_true", help="Show database schema")
    db_group.add_argument("--db-summary", action="store_true", help="Show summary of stored data")
    db_group.add_argument("--db-search", type=str, metavar="KEYWORD", help="Search articles by keyword")

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

    trends = parser.add_argument_group("Trend analysis")
    trends.add_argument("--trends", action="store_true", help="Analyze trends over a period")
    trends.add_argument("--trend-keyword", type=str, metavar="KEYWORD", help="Focus trend analysis on a keyword")
    trends.add_argument("--save-trend-interpretation", type=str, nargs=2, metavar=("HASH", "TEXT"), help="Save LLM trend interpretation")

    digest = parser.add_argument_group("Interest digest")
    digest.add_argument("--digest", action="store_true", help="Generate period digest from interest files")
    digest.add_argument("--interests-dir", type=str, metavar="PATH", help="Directory with interest .md files")

    summarize = parser.add_argument_group("Summarization")
    summarize.add_argument("--summarize-candidates", action="store_true", help="List articles pending summarization")
    summarize.add_argument("--summarize-save", type=str, metavar="PATH", help="Save summarization results from JSON file")
    summarize.add_argument("--summarize-status", action="store_true", help="Show summarization progress")
    summarize.add_argument("--batch-size", type=int, default=100, metavar="N", help="Batch size for candidates")

    interesting = parser.add_argument_group("Interesting / Read flags")
    interesting.add_argument("--mark-interesting", type=int, nargs="+", metavar="ID", help="Mark article(s) as interesting")
    interesting.add_argument("--unmark-interesting", type=int, nargs="+", metavar="ID", help="Unmark article(s) as interesting")
    interesting.add_argument("--mark-read", type=int, nargs="+", metavar="ID", help="Mark article(s) as read")
    interesting.add_argument("--unmark-read", type=int, nargs="+", metavar="ID", help="Unmark article(s) as read")
    interesting.add_argument("--list-interesting", action="store_true", help="List interesting articles")
    interesting.add_argument("--list-unread", action="store_true", help="List unread articles")
    interesting.add_argument("--generate-query-from-interesting", action="store_true", help="Generate interest query from marked articles")

    xlsx = parser.add_argument_group("Excel export / import")
    xlsx.add_argument("--export-xlsx", action="store_true", help="Export articles to Excel")
    xlsx.add_argument("--import-xlsx", type=str, metavar="PATH", help="Import article flags from Excel file")
    xlsx.add_argument("--filter", type=str, choices=["all", "unread", "interesting"], default="all", help="Filter for export")

    config = parser.add_argument_group("Configuration")
    config.add_argument("--workers", type=int, help="Parallel workers")
    config.add_argument("--delay", type=float, nargs=2, metavar=("MIN", "MAX"), help="Request delay range")
    config.add_argument("--timeout", type=int, help="Request timeout")
    config.add_argument("--output", "-o", default="data", help="Output directory")
    config.add_argument("--db", help="Path to database")
    config.add_argument("--verbose", "-v", action="store_true", help="Debug logging")
    config.add_argument("--json", action="store_true", help="Output as JSON")

    _add_date_validator(parser)
    return parser


def _add_date_validator(parser):
    def _validate_date(value):
        try:
            datetime.strptime(value, "%Y-%m-%d").date()
            return value
        except ValueError:
            raise argparse.ArgumentTypeError(f"Invalid date format: '{value}'. Use YYYY-MM-DD.")

    orig_parse_known_args = parser.parse_known_args

    def _patched_parse_known_args(args=None, namespace=None):
        ns, argv = orig_parse_known_args(args, namespace)
        if ns.since:
            _validate_date(ns.since)
        if ns.until:
            _validate_date(ns.until)
        return ns, argv

    parser.parse_known_args = _patched_parse_known_args


def main(argv: list[str] | None = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if args.verbose:
        log_level = "DEBUG"
    else:
        log_level = "INFO"
    setup_logging(log_level)

    db_path = args.db or "data/hackaday.db"
    db = Database(db_path)

    request_cfg = RequestConfig()
    if args.workers:
        request_cfg.parallel_workers = args.workers
    if args.delay:
        request_cfg.delay_min, request_cfg.delay_max = args.delay
    if args.timeout:
        request_cfg.timeout = args.timeout

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
        if args.category:
            info = db.get_category_info(args.category)
            session = db.get_session_info(args.category)
            if args.json:
                print(json.dumps({"category": args.category, "info": dict(info) if info else None, "session": dict(session) if session else None}, indent=2, ensure_ascii=False))
                return 0
            if not info or info["total_articles"] == 0:
                print(f"No articles for category '{args.category}'.")
                return 0
            print(f"\nCategory: {args.category}")
            print(f"  Articles: {info['total_articles']}")
            print(f"  Full texts: {info['full_text_count']}")
            print(f"  Date range: {info['earliest']} \u2014 {info['latest']}")
            if session:
                print(f"  Last session: #{session['id']} ({session['status']})")
                print(f"    Started: {session['started_at']}")
                print(f"    Pages: {session['total_pages']}, Articles: {session['total_found']}")
        else:
            cats = db.get_categories()
            if args.json:
                print(json.dumps(cats, indent=2, ensure_ascii=False))
                return 0
            if not cats:
                print("No articles in database.")
                return 0
            print(f"\nStored categories ({len(cats)}):")
            print("-" * 50)
            for c in cats:
                print(f"  {c['name']:25s} {c['count']} articles")
        return 0

    if args.db_search:
        if not args.db_search.strip():
            logger.error("--db-search requires a non-empty keyword")
            return 1
        results = db.search_articles(args.db_search, args.category)
        if args.json:
            print(json.dumps(results, indent=2, ensure_ascii=False))
            return 0
        if not results:
            print(f"No articles found matching '{args.db_search}'.")
            return 0
        print(f"\nFound {len(results)} article(s) matching '{args.db_search}':")
        print()
        for i, r in enumerate(results, 1):
            tags = ", ".join(r["tags"]) if r["tags"] else "\u2014"
            print(f"{i}. {r['title']} ({r['date']})")
            print(f"   Category: {r['category']}  Author: {r['author'] or '?'}")
            print(f"   Tags: {tags}")
            if r["excerpt"]:
                excerpt = r["excerpt"][:200] + "\u2026" if len(r["excerpt"]) > 200 else r["excerpt"]
                print(f"   {excerpt}")
            print(f"   URL: {r['url']}")
            if r["content_preview"]:
                preview = r["content_preview"][:200] + "\u2026" if len(r["content_preview"]) > 200 else r["content_preview"]
                print(f"   Preview: {preview}")
            print()
        return 0

    if args.list_categories:
        print("\nFetching available categories from Hackaday...")
        categories = fetch_available_categories(request_cfg)
        print(f"\n{'Slug':30s} Name")
        print("-" * 60)
        for slug, name in categories:
            print(f"  {slug:30s} {name}")
        return 0

    if args.info:
        show_info(db, args.category)
        return 0

    if args.latest:
        if not args.category:
            logger.error("--category is required for --latest")
            return 1
        articles = db.list_latest_articles(args.category, args.latest)
        if not articles:
            print(f"No articles found for category '{args.category}'.")
            return 1
        if args.json:
            print(json.dumps(articles, indent=2, ensure_ascii=False, default=str))
            return 0
        for a in articles:
            tags = ", ".join(a["tags"]) if a["tags"] else "\u2014"
            i_mark = "[I]" if a.get("is_interesting") else "   "
            r_mark = "[R]" if a.get("is_read") else "   "
            print(f"[{a['id']}] {i_mark}{r_mark} {a['title']} ({a['date']})")
            print(a["url"])
            print(f"Tags: {tags}")
            print()
            if a["excerpt"]:
                excerpt = a["excerpt"][:200] + "\u2026" if len(a["excerpt"]) > 200 else a["excerpt"]
                print(excerpt)
            print()
            print("===")
            print()
        return 0

    if args.since_date:
        if not args.category:
            logger.error("--category is required for --since-date")
            return 1
        latest = db.get_latest_date(args.category)
        if latest:
            print(latest)
        else:
            print("NONE")
        return 0

    if args.export_json:
        if not args.category:
            logger.error("--category is required for --export-json")
            return 1
        output = export_json(db, args.category, args.output, args.since)
        logger.info("Exported to %s", output)
        return 0

    # New mode handlers
    if args.search:
        return _handle_search(args, db)
    if args.trends:
        return _handle_trends(args, db)
    if args.digest:
        return _handle_digest(args, db)
    if args.save_trend_interpretation:
        params_hash, interpretation = args.save_trend_interpretation
        period_start = args.since or "2000-01-01"
        period_end = args.until or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        save_trend_interpretation(db, args.category, params_hash, period_start, period_end, interpretation)
        print("Trend interpretation saved.")
        return 0
    if args.summarize_candidates or args.summarize_save or args.summarize_status:
        return _handle_summarize(args, db)

    # Interesting / Read flags
    if (args.mark_interesting is not None or args.unmark_interesting is not None
            or args.mark_read is not None or args.unmark_read is not None
            or args.list_interesting or args.list_unread
            or args.generate_query_from_interesting
            or args.export_xlsx or args.import_xlsx):
        return _handle_interesting(args, db)

    # Analysis pipeline (legacy/advanced)
    if (args.search_candidates or args.search_save or args.search_save_stdin or args.search_report
            or args.search_status or args.search_skip_filter):
        return _handle_search_pipeline(args, db)

    if not args.category:
        parser.print_help()
        return 1

    if args.dry_run:
        rate_limiter = AdaptiveRateLimiter(request_cfg)
        base_url = f"https://hackaday.com/category/{args.category}"
        logger.info("DRY RUN \u2014 fetching %s", base_url)
        html = fetch_html(base_url, request_cfg, rate_limiter)

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        total, per_page = get_first_page_info(soup)
        articles = parse_archive_page(html)
        errors = validate_articles(articles)
        print(f"\n{'=' * 60}")
        print(f"DRY RUN \u2014 Validation Report")
        print(f"{'=' * 60}")
        print(f"Category:      {args.category}")
        print(f"Counter says:  {total} total articles")
        print(f"Per page:      {per_page}")
        print(f"Parsed:        {len(articles)} articles on first page")
        if errors:
            print(f"\nErrors ({len(errors)}):")
            for e in errors:
                print(f"  ! {e}")
        else:
            print(f"\n  Validation: PASSED")
        print(f"\nSample articles:")
        for a in articles[:3]:
            print(f"  \u2022 {a['title']}")
            print(f"    Date: {a['date']}  Tags: {', '.join(a['tags'])}")
            print(f"    URL:  {a['url']}")
            print()
        return 1 if errors else 0

    if args.reset:
        info = db.get_category_info(args.category)
        count = info["total_articles"] if info else 0
        print(f"\nWARNING: This will DELETE {count} article(s) and all associated data for '{args.category}'.")
        print("This operation cannot be undone. The database will need to be scraped again from scratch.")
        confirm = input("Type 'yes' to confirm: ").strip().lower()
        if confirm != "yes":
            logger.info("Reset cancelled by user")
            print("Reset cancelled.")
            return 0
        db.reset_category(args.category)
        logger.info("Reset category '%s' (%d articles deleted)", args.category, count)
        print(f"Category '{args.category}' has been reset.")

    if args.full_text_only:
        last_session = db.get_last_session(args.category)
        if not last_session:
            logger.error("No existing session for '%s'. Run without --full-text-only first.", args.category)
            return 1
        session_id = db.create_session(args.category)
        scrape_full_articles(db, args.category, session_id, request_cfg, args.since, args.skip_comments)
        db.finish_session(session_id, "completed")
        show_info(db, args.category)
        return 0

    session_id = db.create_session(args.category)
    logger.info("Session %d started for category '%s'", session_id, args.category)

    try:
        total_found = scrape_archive_pages(db, args.category, session_id, request_cfg, dry_run=False, max_pages=args.max_pages, until=args.until)

        if args.metadata_only:
            db.finish_session(session_id, "completed", total_found=total_found)
            logger.info("Scrape complete (metadata only): %d articles", total_found)
        else:
            scrape_full_articles(db, args.category, session_id, request_cfg, args.since, args.skip_comments)
            db.finish_session(session_id, "completed", total_found=total_found)
            logger.info("Full scrape complete: %d articles", total_found)

        show_info(db, args.category)
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