# Gig 4 portfolio: Python automation and scraping samples

Three complete, runnable sample projects for the gig *"I will write a python script to automate tasks or scrape website data"*. Each folder has its own README, `requirements.txt`, config, offline tests, the real output of a real run (`output/`) and a terminal screenshot made from that run's captured log (`screenshots/`).

| # | Project | Shows | Real run (2026-09-26) |
|---|---|---|---|
| 01 | [`01-books-scraper`](01-books-scraper/) | Paginated e-commerce scraper for books.toscrape.com (a practice site): every category and page, product-page details, CSV + formatted Excel, retries with a second pass, rate limit, robots.txt, logging, CLI + optional TOML config | 1,000 products, 50 categories, 0 errors, 20.6 min |
| 02 | [`02-hn-digest`](02-hn-digest/) | Official Hacker News API → keyword filter → Excel/CSV (Google-Sheets-ready), optional Google Sheets push and SMTP email digest (dry run by default, credentials from env vars) | 100 stories checked, 9 matched, 28.5 s |
| 03 | [`03-file-automation`](03-file-automation/) | Organise a messy folder (sort, rename, de-duplicate, undo log) and merge CSV/XLSX exports into one cleaned workbook with a Summary sheet; Task Scheduler / cron scripts | 3 files, 21 rows → 17 kept, 2 duplicates, 2 rejected |

## Shared building blocks (`core/` in each project)

Copied from the delivery kit in `tools/gig4-python/template/core/`, so real orders use the same tested code:

- `http.py`: `PoliteSession` with urllib3 retries and exponential backoff on 429/5xx/network errors (honours `Retry-After`), a thread-safe rate limiter, robots.txt checks with RFC 9309 wildcard matching (Python's `urllib.robotparser` gets the Hacker News API's rules wrong), timeouts, and one-line retry logging.
- `excel.py`: formatted Excel tables (styled header, frozen row, filters, banding, number formats, fitted widths), key-value summary sheets, protection against formula injection, and a clear error when the file is open in Excel.
- `config.py`: TOML settings plus secrets from environment variables or `.env`, with readable `ConfigError`s.
- `log.py`: console and file logging that doesn't crash on Windows consoles.

## Rules the samples follow

- Only sites that invite scraping practice (books.toscrape.com) or public APIs (Hacker News). robots.txt is respected and requests are spaced (1 s for the site, 0.1 s for the API).
- No personal data collected. Demo data in 03 is fictional.
- No secrets in code: SMTP and Google credentials come only from `.env` (see `02-hn-digest/.env.example`).
- Python 3.10+ (tested on 3.11, Windows). No pandas or matplotlib.

## Re-running everything

```bash
cd 01-books-scraper && pip install -r requirements.txt && python -m pytest -q && python books_scraper.py
cd ../02-hn-digest   && pip install -r requirements.txt && python -m pytest -q && python hn_digest.py --email
cd ../03-file-automation && pip install -r requirements.txt && python -m pytest -q && python make_sample_inbox.py && python file_automator.py run
```

Built with an AI-assisted workflow, then run and tested as documented in each README.
