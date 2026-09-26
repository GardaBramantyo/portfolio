#!/usr/bin/env python3
"""Scrape every book on books.toscrape.com (a sandbox built for scraping practice).

Walks all categories and all their pages, optionally opens each product page for
the exact stock count and UPC, then writes a CSV and a formatted Excel workbook.

Examples:
    python books_scraper.py                         # everything, with product details
    python books_scraper.py --no-details            # listing pages only (~70 requests)
    python books_scraper.py --categories "Travel,Poetry" --delay 1.5
    python books_scraper.py --list-categories
    python books_scraper.py --config config.toml    # settings from a file
"""
from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from openpyxl import Workbook

from core.config import ConfigError, load_toml
from core.excel import save_workbook, write_key_values, write_table
from core.http import PoliteSession, RobotsDisallowed, describe_error
from core.log import setup_logging

DEFAULT_BASE_URL = "https://books.toscrape.com/"
DEFAULT_USER_AGENT = "books-toscrape-sample/1.0 (python-requests; portfolio demo)"
RATINGS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}

try:  # lxml is faster; fall back to the stdlib parser if its DLL can't load
    import lxml  # noqa: F401

    PARSER = "lxml"
except ImportError:  # pragma: no cover
    PARSER = "html.parser"

log = logging.getLogger("books")


@dataclass
class Book:
    category: str
    title: str
    price_gbp: float
    rating: int
    in_stock: bool
    stock_qty: int | None
    upc: str
    reviews: int | None
    product_url: str
    image_url: str
    scraped_at: str


@dataclass
class RunStats:
    categories: int = 0
    listing_pages: int = 0
    detail_pages: int = 0
    errors: int = 0          # failures left after the second pass
    recovered: int = 0       # failures fixed by the second pass
    failed_listings: list[tuple[str, str, int]] = field(default_factory=list)  # (category, url, page)
    failed_details: list[Book] = field(default_factory=list)


# --------------------------------------------------------------------- parsing
def soup_of(html: bytes) -> BeautifulSoup:
    # Pass bytes so BeautifulSoup reads the <meta charset>; the server sends no charset header.
    return BeautifulSoup(html, PARSER)


def parse_price(text: str) -> float:
    match = re.search(r"(\d+(?:\.\d+)?)", text.replace(",", ""))
    if not match:
        raise ValueError(f"no price in {text!r}")
    return float(match.group(1))


def parse_categories(html: bytes, base_url: str) -> list[tuple[str, str]]:
    soup = soup_of(html)
    links = soup.select("div.side_categories ul li ul li a")
    return [(a.get_text(strip=True), urljoin(base_url, a["href"])) for a in links]


def parse_listing(html: bytes, page_url: str, category: str) -> tuple[list[Book], str | None]:
    soup = soup_of(html)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    books: list[Book] = []
    for pod in soup.select("article.product_pod"):
        link = pod.select_one("h3 a")
        rating_tag = pod.select_one("p.star-rating")
        rating_word = next((c for c in (rating_tag.get("class", []) if rating_tag else []) if c in RATINGS), None)
        img = pod.select_one("img")
        availability = pod.select_one("p.availability").get_text(" ", strip=True)
        books.append(
            Book(
                category=category,
                title=link.get("title") or link.get_text(strip=True),
                price_gbp=parse_price(pod.select_one("p.price_color").get_text()),
                rating=RATINGS.get(rating_word, 0),
                in_stock="in stock" in availability.lower(),
                stock_qty=None,
                upc="",
                reviews=None,
                product_url=urljoin(page_url, link["href"]),
                image_url=urljoin(page_url, img["src"]) if img else "",
                scraped_at=now,
            )
        )
    next_link = soup.select_one("li.next a")
    return books, (urljoin(page_url, next_link["href"]) if next_link else None)


def parse_detail(html: bytes) -> dict[str, str]:
    soup = soup_of(html)
    table = {th.get_text(strip=True): td.get_text(strip=True) for th, td in
             ((row.th, row.td) for row in soup.select("table.table-striped tr")) if th and td}
    return table


def apply_detail(book: Book, detail: dict[str, str]) -> None:
    book.upc = detail.get("UPC", "")
    availability = detail.get("Availability", "")
    qty = re.search(r"\((\d+) available\)", availability)
    book.stock_qty = int(qty.group(1)) if qty else 0
    book.in_stock = book.stock_qty > 0 or "in stock" in availability.lower()
    reviews = detail.get("Number of reviews", "")
    book.reviews = int(reviews) if reviews.isdigit() else None


# -------------------------------------------------------------------- scraping
def iter_category(http: PoliteSession, name: str, url: str, max_pages: int | None, stats: RunStats,
                  start_page: int = 1) -> Iterator[Book]:
    page, page_url = start_page, url
    while page_url:
        try:
            books, next_url = parse_listing(http.get(page_url).content, page_url, name)
        except RobotsDisallowed:
            raise
        except Exception as exc:  # noqa: BLE001 - remember it, retry in the second pass
            stats.failed_listings.append((name, page_url, page))
            log.error("  %s page %d failed: %s (will retry at the end)", name, page, describe_error(exc))
            return
        stats.listing_pages += 1
        log.debug("  %s page %d: %d books", name, page, len(books))
        yield from books
        if max_pages and page >= max_pages:
            break
        page, page_url = page + 1, next_url


def fetch_detail(http: PoliteSession, book: Book, stats: RunStats, final: bool = False) -> bool:
    try:
        apply_detail(book, parse_detail(http.get(book.product_url).content))
    except RobotsDisallowed:
        raise
    except Exception as exc:  # noqa: BLE001
        if final:
            log.error("  product page still failing: %s (%s)", book.product_url, describe_error(exc))
        else:
            stats.failed_details.append(book)
            log.error("  product page failed: %s (%s; will retry at the end)", book.title[:40], describe_error(exc))
        return False
    stats.detail_pages += 1
    return True


def second_pass(http: PoliteSession, args: argparse.Namespace, stats: RunStats, books: list[Book], seen: set[str]) -> None:
    """Retry everything that failed once more, after a pause (network blips, brief outages)."""
    listings, details = stats.failed_listings, stats.failed_details
    if not listings and not details:
        return
    log.info("Second pass: retrying %d listing page(s) and %d product page(s) after a %ds pause",
             len(listings), len(details), args.retry_pause)
    time.sleep(args.retry_pause)
    stats.failed_listings, stats.failed_details = [], []
    for name, url, page in listings:
        before = len(stats.failed_listings)
        found = [b for b in iter_category(http, name, url, args.max_pages, stats, start_page=page) if b.product_url not in seen]
        new_failures = len(stats.failed_listings) - before
        stats.errors += new_failures
        if new_failures and not found:
            continue
        stats.recovered += 1
        for book in found:
            if args.details and not fetch_detail(http, book, stats, final=True):
                stats.errors += 1
            seen.add(book.product_url)
        books.extend(found)
        log.info("  recovered %s page %d+ (%d books)", name, page, len(found))
    for book in details:
        if fetch_detail(http, book, stats, final=True):
            stats.recovered += 1
        else:
            stats.errors += 1
    log.info("Second pass done: %d recovered, %d still failing", stats.recovered, stats.errors)


def scrape(args: argparse.Namespace) -> tuple[list[Book], RunStats]:
    stats = RunStats()
    books: list[Book] = []
    with PoliteSession(args.user_agent, min_interval=args.delay, max_retries=args.retries, timeout=args.timeout) as http:
        categories = parse_categories(http.get(args.base_url).content, args.base_url)
        log.info("Found %d categories", len(categories))
        if args.list_categories:
            for name, _ in categories:
                print(name)
            return [], stats
        if args.categories:
            wanted = {c.strip().lower() for c in args.categories.split(",") if c.strip()}
            unknown = wanted - {n.lower() for n, _ in categories}
            if unknown:
                raise SystemExit(f"Unknown categories: {', '.join(sorted(unknown))}. Use --list-categories.")
            categories = [(n, u) for n, u in categories if n.lower() in wanted]

        seen: set[str] = set()
        try:
            for i, (name, url) in enumerate(categories, 1):
                stats.categories += 1
                found = [b for b in iter_category(http, name, url, args.max_pages, stats) if b.product_url not in seen]
                if args.details:
                    for book in found:
                        fetch_detail(http, book, stats)
                for book in found:
                    seen.add(book.product_url)
                books.extend(found)
                log.info("[%2d/%d] %-22s %3d books  (total %d)", i, len(categories), name, len(found), len(books))
            second_pass(http, args, stats, books, seen)
        except KeyboardInterrupt:
            log.warning("Interrupted: saving the %d books scraped so far", len(books))
            stats.errors += len(stats.failed_listings) + len(stats.failed_details)
        log.info("HTTP requests sent: %d (incl. robots.txt)", http.request_count)
    return books, stats


# ---------------------------------------------------------------------- output
def write_csv(books: list[Book], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:  # BOM so Excel reads £ correctly
        writer = csv.DictWriter(fh, fieldnames=[f.name for f in fields(Book)])
        writer.writeheader()
        writer.writerows(asdict(b) for b in books)


def category_summary(books: list[Book]) -> list[list[object]]:
    groups: dict[str, list[Book]] = defaultdict(list)
    for b in books:
        groups[b.category].append(b)
    rows = []
    for name, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        prices = [b.price_gbp for b in items]
        stock = sum(b.stock_qty or 0 for b in items)
        rows.append([
            name, len(items), round(sum(prices) / len(prices), 2), min(prices), max(prices),
            round(sum(b.rating for b in items) / len(items), 2), stock,
            round(sum(b.price_gbp * (b.stock_qty or 0) for b in items), 2),
        ])
    return rows


def write_excel(books: list[Book], stats: RunStats, args: argparse.Namespace, seconds: float, path: Path) -> None:
    wb = Workbook()
    headers = ["Category", "Title", "Price (GBP)", "Rating", "In stock", "Stock qty", "UPC", "Reviews", "Product URL", "Scraped at (UTC)"]
    rows = [[b.category, b.title, b.price_gbp, b.rating, "Yes" if b.in_stock else "No", b.stock_qty, b.upc,
             b.reviews, b.product_url, b.scraped_at] for b in books]
    write_table(wb, "Books", headers, rows, number_formats={"Price (GBP)": '"£"#,##0.00'},
                widths={"Title": 48, "Product URL": 40})
    write_table(
        wb, "By category",
        ["Category", "Books", "Avg price", "Min price", "Max price", "Avg rating", "Units in stock", "Stock value (GBP)"],
        category_summary(books),
        number_formats={k: '"£"#,##0.00' for k in ("Avg price", "Min price", "Max price", "Stock value (GBP)")},
        style="TableStyleMedium9",
    )
    write_key_values(wb, "Run info", [
        ("Source", args.base_url),
        ("Finished (UTC)", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")),
        ("Books", len(books)),
        ("Categories", stats.categories),
        ("Listing pages", stats.listing_pages),
        ("Product pages", stats.detail_pages),
        ("Recovered on second pass", stats.recovered),
        ("Errors", stats.errors),
        ("Delay between requests (s)", args.delay),
        ("Run time (s)", round(seconds, 1)),
    ], heading="Scrape run")
    save_workbook(wb, path)


# ------------------------------------------------------------------------- CLI
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Scrape books.toscrape.com into CSV + Excel.")
    p.add_argument("--config", help="optional TOML file with the same option names (CLI flags win)")
    p.add_argument("--base-url", default=None, help=f"site root (default {DEFAULT_BASE_URL})")
    p.add_argument("--categories", default=None, help='comma-separated category names, e.g. "Travel,Poetry"')
    p.add_argument("--list-categories", action="store_true", help="print category names and exit")
    p.add_argument("--max-pages", type=int, default=None, help="max listing pages per category")
    p.add_argument("--details", dest="details", action="store_true", default=None, help="open product pages for stock qty/UPC (default)")
    p.add_argument("--no-details", dest="details", action="store_false", help="listing pages only (faster)")
    p.add_argument("--delay", type=float, default=None, help="seconds between requests (default 1.0)")
    p.add_argument("--retries", type=int, default=None, help="retries per request on 429/5xx/network errors (default 4)")
    p.add_argument("--timeout", type=float, default=None, help="request timeout in seconds (default 20)")
    p.add_argument("--retry-pause", type=int, default=None, help="pause before re-trying failed pages at the end (default 30s)")
    p.add_argument("--user-agent", default=None, help="User-Agent header sent to the site")
    p.add_argument("--out-dir", default=None, help="output folder (default ./output)")
    p.add_argument("--log-file", default=None, help="also write the log here (default <out-dir>/run.log)")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging (every request)")
    return p


def resolve_args(argv: list[str] | None = None) -> argparse.Namespace:
    args = build_parser().parse_args(argv)
    cfg = load_toml(args.config) if args.config else {}
    defaults = {"base_url": DEFAULT_BASE_URL, "categories": None, "max_pages": None, "details": True,
                "delay": 1.0, "retries": 4, "timeout": 20.0, "retry_pause": 30, "user_agent": DEFAULT_USER_AGENT, "out_dir": "output"}
    for key, default in defaults.items():
        if getattr(args, key) is None:
            setattr(args, key, cfg.get(key, default))
    if args.delay < 0.5:
        raise ConfigError("--delay below 0.5s is not allowed: stay polite to the site")
    if args.log_file is None:
        args.log_file = str(Path(args.out_dir) / "run.log")
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        args = resolve_args(argv)
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    setup_logging(args.verbose, None if args.list_categories else args.log_file)
    started = time.monotonic()
    log.info("Scraping %s (delay %.1fs, details=%s)", args.base_url, args.delay, args.details)
    try:
        books, stats = scrape(args)
    except RobotsDisallowed as exc:
        log.error("Stopped: %s", exc)
        return 3
    except Exception as exc:  # noqa: BLE001
        log.error("Could not start: %s", describe_error(exc))
        return 1
    if args.list_categories:
        return 0
    if not books:
        log.error("No books scraped; nothing written")
        return 1

    out = Path(args.out_dir)
    elapsed = time.monotonic() - started
    write_csv(books, out / "books.csv")
    write_excel(books, stats, args, elapsed, out / "books.xlsx")
    stock = f"{sum(b.stock_qty or 0 for b in books):,} units in stock" if args.details else "stock qty not collected (--no-details)"
    log.info("Saved %d books -> %s and %s", len(books), out / "books.csv", out / "books.xlsx")
    log.info("Summary: %d categories, %d listing pages, %d product pages, %d errors, %s, %.0fs",
             stats.categories, stats.listing_pages, stats.detail_pages, stats.errors, stock, elapsed)
    if stats.errors:
        log.warning("%d page(s) failed twice; those books have empty stock/UPC fields. Re-run to fill them.", stats.errors)
    return 0 if stats.errors == 0 else 4


if __name__ == "__main__":
    sys.exit(main())
