#!/usr/bin/env python3
"""Hacker News top stories -> keyword filter -> CSV/Excel report (+ optional email, Google Sheet).

Uses the official, public Hacker News API (https://github.com/HackerNews/API).
No login, no personal data: only story titles, links, scores and comment counts.

Examples:
    python hn_digest.py                                   # uses config.toml
    python hn_digest.py --keywords "python,ai,rust" --top 60 --min-score 50
    python hn_digest.py --email                           # build the email, DRY RUN (nothing sent)
    python hn_digest.py --email --send                    # really send (SMTP settings from .env)
    python hn_digest.py --sheet-id <GOOGLE_SHEET_ID>      # also push matches to a Google Sheet
"""
from __future__ import annotations

import argparse
import csv
import html
import logging
import re
import smtplib
import ssl
import sys
import time
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from urllib.parse import urlsplit

from openpyxl import Workbook

from core.config import ConfigError, env, env_int, load_dotenv_if_present, load_toml
from core.excel import save_workbook, write_key_values, write_table
from core.http import PoliteSession
from core.log import setup_logging

API = "https://hacker-news.firebaseio.com/v0"
USER_AGENT = "hn-digest-sample/1.0 (python-requests; portfolio demo)"
log = logging.getLogger("hn")


@dataclass
class Story:
    rank: int
    id: int
    title: str
    domain: str
    url: str
    score: int
    comments: int
    posted_utc: str
    age_hours: float
    type: str
    hn_url: str
    matched: str


# ------------------------------------------------------------------- fetching
def fetch_stories(http: PoliteSession, top: int) -> list[Story]:
    ids = http.get_json(f"{API}/topstories.json")[:top]
    log.info("Top stories endpoint returned %d ids; fetching %d items", len(ids), len(ids))
    now = time.time()
    stories: list[Story] = []
    for rank, item_id in enumerate(ids, 1):
        try:
            item = http.get_json(f"{API}/item/{item_id}.json")
        except Exception as exc:  # noqa: BLE001 - one bad item must not kill the report
            log.warning("  item %s skipped: %s", item_id, exc)
            continue
        if not item or item.get("deleted") or item.get("dead"):
            continue
        hn_url = f"https://news.ycombinator.com/item?id={item_id}"
        url = item.get("url") or hn_url
        stories.append(Story(
            rank=rank,
            id=item_id,
            title=item.get("title", "").strip(),
            domain=(urlsplit(url).netloc.removeprefix("www.") if item.get("url") else "news.ycombinator.com"),
            url=url,
            score=int(item.get("score", 0)),
            comments=int(item.get("descendants", 0) or 0),
            posted_utc=datetime.fromtimestamp(item.get("time", now), timezone.utc).strftime("%Y-%m-%d %H:%M"),
            age_hours=round((now - item.get("time", now)) / 3600, 1),
            type=item.get("type", "story"),
            hn_url=hn_url,
            matched="",
        ))
        if rank % 25 == 0:
            log.info("  fetched %d/%d", rank, len(ids))
    return stories


def keyword_patterns(keywords: list[str]) -> dict[str, re.Pattern[str]]:
    # Whole-word, case-insensitive: "ai" matches "AI agents" but not "said".
    return {kw: re.compile(rf"(?<![A-Za-z0-9]){re.escape(kw)}(?![A-Za-z0-9])", re.IGNORECASE) for kw in keywords}


def apply_filter(stories: list[Story], keywords: list[str], min_score: int) -> list[Story]:
    patterns = keyword_patterns(keywords)
    for story in stories:
        haystack = f"{story.title} {story.domain}"
        story.matched = ", ".join(kw for kw, pat in patterns.items() if pat.search(haystack))
    return sorted((s for s in stories if s.matched and s.score >= min_score), key=lambda s: -s.score)


# --------------------------------------------------------------------- output
def write_csv(stories: list[Story], path: Path) -> None:
    """UTF-8 CSV with ISO dates and one header row: imports cleanly into Google Sheets."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=[f.name for f in fields(Story)])
        writer.writeheader()
        writer.writerows(asdict(s) for s in stories)


HEADERS = ["Rank", "Title", "Domain", "Score", "Comments", "Posted (UTC)", "Age (h)", "Matched keywords", "Link", "HN discussion"]


def as_row(s: Story) -> list[object]:
    return [s.rank, s.title, s.domain, s.score, s.comments, s.posted_utc, s.age_hours, s.matched, s.url, s.hn_url]


def keyword_summary(matches: list[Story], keywords: list[str]) -> list[list[object]]:
    rows = []
    for kw in keywords:
        hits = [s for s in matches if kw in [m.strip() for m in s.matched.split(",")]]
        top = max(hits, key=lambda s: s.score) if hits else None
        rows.append([kw, len(hits), round(sum(s.score for s in hits) / len(hits)) if hits else 0,
                     top.title if top else "", top.score if top else None])
    return rows


def write_excel(all_stories: list[Story], matches: list[Story], keywords: list[str], min_score: int, path: Path) -> None:
    wb = Workbook()
    write_table(wb, "Matches", HEADERS, [as_row(s) for s in matches], widths={"Title": 60, "Link": 40, "HN discussion": 22})
    write_table(wb, "Keyword summary", ["Keyword", "Stories", "Avg score", "Top story", "Top score"],
                keyword_summary(matches, keywords), widths={"Top story": 60}, style="TableStyleMedium9")
    write_table(wb, "All top stories", HEADERS, [as_row(s) for s in all_stories],
                widths={"Title": 60, "Link": 40, "HN discussion": 22}, style="TableStyleLight9")
    write_key_values(wb, "Run info", [
        ("Source", "Hacker News API (topstories)"),
        ("Generated (UTC)", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")),
        ("Stories checked", len(all_stories)),
        ("Keywords", ", ".join(keywords)),
        ("Minimum score", min_score),
        ("Matches", len(matches)),
    ], heading="HN keyword report")
    save_workbook(wb, path)


def build_email(matches: list[Story], keywords: list[str], sender: str, recipients: list[str]) -> EmailMessage:
    today = datetime.now(timezone.utc).strftime("%d %b %Y")
    msg = EmailMessage()
    msg["Subject"] = f"HN digest {today}: {len(matches)} stories on {', '.join(keywords)}"
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain="hn-digest.local")

    lines = [f"{len(matches)} Hacker News top stories matched: {', '.join(keywords)}", ""]
    for s in matches[:25]:
        lines += [f"[{s.score} pts, {s.comments} comments] {s.title}", f"  {s.url}", ""]
    msg.set_content("\n".join(lines))

    items = "".join(
        f'<tr><td style="padding:6px 10px;color:#b45309;font-weight:700;text-align:right">{s.score}</td>'
        f'<td style="padding:6px 10px"><a href="{html.escape(s.url)}" style="color:#111827;text-decoration:none;font-weight:600">'
        f'{html.escape(s.title)}</a><br><span style="color:#6b7280;font-size:12px">{html.escape(s.domain)} &middot; '
        f'{s.comments} comments &middot; <a href="{s.hn_url}" style="color:#6b7280">discussion</a> &middot; '
        f'{html.escape(s.matched)}</span></td></tr>'
        for s in matches[:25]
    )
    msg.add_alternative(
        f'<div style="font-family:Arial,sans-serif;max-width:640px"><h2 style="margin:0 0 4px">HN digest, {today}</h2>'
        f'<p style="color:#6b7280;margin:0 0 16px">{len(matches)} top stories matched: {html.escape(", ".join(keywords))}</p>'
        f'<table style="border-collapse:collapse;width:100%">{items}</table></div>',
        subtype="html",
    )
    return msg


def send_email(msg: EmailMessage) -> None:
    host = env("SMTP_HOST", required=True)
    port = env_int("SMTP_PORT", 587)
    security = (env("SMTP_SECURITY", "starttls") or "starttls").lower()
    user, password = env("SMTP_USER"), env("SMTP_PASSWORD")
    if security not in ("starttls", "ssl", "none"):
        raise ConfigError("SMTP_SECURITY must be starttls, ssl or none")
    context = ssl.create_default_context()
    smtp_cls = smtplib.SMTP_SSL if security == "ssl" else smtplib.SMTP
    kwargs = {"context": context} if security == "ssl" else {}
    with smtp_cls(host, port, timeout=30, **kwargs) as smtp:
        if security == "starttls":
            smtp.starttls(context=context)
        if user and password:
            smtp.login(user, password)
        smtp.send_message(msg)


def push_to_google_sheet(stories: list[Story], sheet_id: str, worksheet: str) -> int:
    """Replace a worksheet's contents with the matches. Needs gspread + a service-account key file."""
    try:
        import gspread
    except ImportError as exc:
        raise ConfigError("Google Sheets output needs gspread: pip install gspread") from exc
    key_file = env("GOOGLE_SERVICE_ACCOUNT_FILE", required=True)
    if not Path(key_file).exists():
        raise ConfigError(f"GOOGLE_SERVICE_ACCOUNT_FILE points to a missing file: {key_file}")
    client = gspread.service_account(filename=key_file)
    sheet = client.open_by_key(sheet_id)
    try:
        ws = sheet.worksheet(worksheet)
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet(title=worksheet, rows=max(100, len(stories) + 1), cols=len(HEADERS))
    values = [HEADERS] + [as_row(s) for s in stories]
    ws.clear()
    ws.update(values=values, range_name="A1")
    return len(stories)


def mask(address: str) -> str:
    name, _, domain = address.partition("@")
    return f"{name[:2]}***@{domain}" if domain else "***"


# ------------------------------------------------------------------------ CLI
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Hacker News keyword report -> CSV, Excel, email, Google Sheets.")
    p.add_argument("--config", default="config.toml", help="TOML settings file (default config.toml, optional)")
    p.add_argument("--keywords", help='comma-separated, e.g. "python,ai,open source"')
    p.add_argument("--top", type=int, help="how many top stories to check (1-500, default 100)")
    p.add_argument("--min-score", type=int, help="ignore stories below this score (default 0)")
    p.add_argument("--out-dir", help="output folder (default ./output)")
    p.add_argument("--email", action="store_true", help="build the email digest (dry run unless --send)")
    p.add_argument("--send", action="store_true", help="actually send the email via SMTP settings in .env")
    p.add_argument("--sheet-id", help="Google Sheet ID to push matches to (needs GOOGLE_SERVICE_ACCOUNT_FILE)")
    p.add_argument("--worksheet", default="HN matches", help="worksheet/tab name in the Google Sheet")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def resolve(argv: list[str] | None) -> argparse.Namespace:
    args = build_parser().parse_args(argv)
    cfg = load_toml(args.config, required=False)
    keywords = args.keywords if args.keywords is not None else cfg.get("keywords", ["python"])
    if isinstance(keywords, str):
        keywords = keywords.split(",")
    args.keywords = [k.strip() for k in keywords if k.strip()]
    if not args.keywords:
        raise ConfigError("No keywords given. Use --keywords or set keywords in config.toml")
    args.top = args.top if args.top is not None else int(cfg.get("top", 100))
    if not 1 <= args.top <= 500:
        raise ConfigError("--top must be between 1 and 500 (the API returns at most 500)")
    args.min_score = args.min_score if args.min_score is not None else int(cfg.get("min_score", 0))
    args.out_dir = Path(args.out_dir or cfg.get("out_dir", "output"))
    args.delay = float(cfg.get("delay", 0.1))
    if args.send and not args.email:
        raise ConfigError("--send only makes sense together with --email")
    return args


def main(argv: list[str] | None = None) -> int:
    load_dotenv_if_present()
    try:
        args = resolve(argv)
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    setup_logging(args.verbose, args.out_dir / "run.log")
    log.info("Keywords: %s | top %d | min score %d", ", ".join(args.keywords), args.top, args.min_score)
    started = time.monotonic()
    try:
        with PoliteSession(USER_AGENT, min_interval=args.delay) as http:
            stories = fetch_stories(http, args.top)
    except Exception as exc:  # noqa: BLE001
        log.error("Could not reach the Hacker News API: %s", exc)
        return 1

    matches = apply_filter(stories, args.keywords, args.min_score)
    write_csv(stories, args.out_dir / "hn_top_stories.csv")
    write_csv(matches, args.out_dir / "hn_matches.csv")
    write_excel(stories, matches, args.keywords, args.min_score, args.out_dir / "hn_report.xlsx")
    log.info("%d of %d stories matched -> %s", len(matches), len(stories), args.out_dir / "hn_report.xlsx")
    for s in matches[:5]:
        log.info("  %4d pts  %s  [%s]", s.score, s.title[:70], s.matched)

    try:
        if args.email:
            sender = env("DIGEST_FROM", "digest@example.com") or "digest@example.com"
            recipients = [r.strip() for r in (env("DIGEST_TO", "you@example.com") or "").split(",") if r.strip()]
            msg = build_email(matches, args.keywords, sender, recipients)
            eml = args.out_dir / "digest_preview.eml"
            eml.write_bytes(bytes(msg))
            (args.out_dir / "digest_preview.html").write_text(msg.get_body(("html",)).get_content(), encoding="utf-8")
            if args.send:
                send_email(msg)
                log.info("Email sent to %s", ", ".join(mask(r) for r in recipients))
            else:
                log.info("DRY RUN: email not sent. Preview saved to %s (add --send to deliver)", eml)
    except ConfigError as exc:
        log.error("%s", exc)
        return 2
    except (smtplib.SMTPException, OSError) as exc:
        log.error("Email failed: %s", exc)
        return 1

    if args.sheet_id:
        try:
            n = push_to_google_sheet(matches, args.sheet_id, args.worksheet)
            log.info("Google Sheet updated: %d rows in tab '%s'", n, args.worksheet)
        except ConfigError as exc:
            log.error("%s", exc)
            return 2
        except Exception as exc:  # noqa: BLE001 - gspread/google-auth raise many types
            log.error("Google Sheet update failed (%s: %s). Is the sheet shared with the service account?",
                      type(exc).__name__, exc)
            return 1

    log.info("Done in %.1fs", time.monotonic() - started)
    return 0


if __name__ == "__main__":
    sys.exit(main())
