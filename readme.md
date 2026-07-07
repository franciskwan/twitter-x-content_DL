# twitter-x-content_DL

<div align="center">

[![license](https://img.shields.io/github/license/franciskwan/twitter-x-content_DL)](LICENSE)
[![python](https://img.shields.io/badge/python-3.10%20to%203.14-blue)](https://www.python.org)
[![build](https://img.shields.io/github/actions/workflow/status/franciskwan/twitter-x-content_DL/ci.yml?branch=main)](https://github.com/franciskwan/twitter-x-content_DL/actions/workflows/ci.yml)

</div>

A toolkit for pulling content out of **X / Twitter** — both the usual GraphQL
data (tweets, threads, search, users, followers) **and** long-form **articles**,
which almost no scraper handles well.

It's a fork of [vladkens/twscrape](https://github.com/vladkens/twscrape)
(MIT). All of upstream's scraping code is preserved as-is; the
article-extraction module is new.

## Why this fork exists

X's long-form **articles** (`https://x.com/<user>/article/<id>`) are not
reachable through any stable GraphQL endpoint:

- `tweet_details` only returns article *metadata* (title, preview, cover image).
- The body lives behind `ArticleEntityByRestId`, whose `queryId` hash
  **rotates periodically** — direct probing returns 422 / 404.

So this fork renders the public article page in headless Chromium with your own
`auth_token` + `ct0` cookies, then walks the rendered DOM. Because it runs the
same JS bundle X's own web app runs, the method is **hash-rotation-proof**.

## Features

**From upstream twscrape**

- Async / await API for running scrapers concurrently
- GraphQL methods: `search`, `tweet_details`, `tweet_thread`,
  `user_by_login`, `followers`, `user_tweets`, …
- Cookie-based login, saved sessions, per-account proxies
- Raw API responses + parsed models

**New in this fork — article extraction**

- `twitter-x-content_DL article <url>` → self-contained **HTML** (default) or
  **Markdown** (`--md`)
- Preserves heading hierarchy, paragraphs, lists, blockquotes, inline images
  (in document order)
- Inline full-resolution images from X's `pbs.twimg.com` CDN
- Video cards as clickable links back to the source tweet (article-embedded
  videos use session-scoped `blob:` URLs that don't survive extraction)
- Filename = `<sanitized_title>_<article_id>.<ext>` — the article's real
  title, not the URL slug
- Python API: `await twscrape.articles.extract(url, cookies) -> Article`

## Installation

```bash
# Core GraphQL scraping only — lightweight, no browser download
pip install twitter-x-content_DL

# + article extraction (adds Playwright + Chromium, ~150 MB)
pip install "twitter-x-content_DL[article]"
python -m playwright install chromium
```

Prefer `uv`? `uv pip install "twitter-x-content_DL[article]"` then
`uv run python -m playwright install chromium`.

Optional `curl` backend for browser-like TLS fingerprinting on the GraphQL
side: `pip install "twitter-x-content_DL[curl]"`.

## Quick start

### 1. GraphQL scraping

```bash
# Add an account from your browser cookies
twitter-x-content_DL add_cookie my_account "auth_token=xxx; ct0=yyy"

# Search, fetch a tweet + its thread, pull a user's tweets
twitter-x-content_DL search "from:xdevelopers lang:en" --limit=20
twitter-x-content_DL tweet_details 1701694747767648500
twitter-x-content_DL tweet_thread 1701694747767648500
twitter-x-content_DL user_tweets 1632207375288254464 --limit=10
```

Accounts with `ct0` activate immediately — no `login_accounts` step. Get the
cookies from x.com → DevTools (F12) → Application → Cookies → copy `auth_token`
and `ct0`.

### 2. Article extraction

```bash
# Renders a self-contained HTML file in the current directory
twitter-x-content_DL article "https://x.com/thedankoe/status/2010751592346030461?s=20"
# Example output (HTML, default):
#   title:   How to fix your entire life in 1 day
#   blocks:  162  (images: 3, videos: 0)
#   words:   5556
#   wrote 35,801 chars -> ./How to fix your entire life in 1 day_2010751592346030461.html

# Markdown instead (same URL, --md)
twitter-x-content_DL article "https://x.com/thedankoe/status/2010751592346030461?s=20" --md
#   wrote 31,558 chars -> ./How to fix your entire life in 1 day_2010751592346030461.md

# Save to a folder, using a named account row
twitter-x-content_DL --db ./accounts.db article \
  "https://x.com/i/article/2073912103778578432" \
  --account backup_account --out ~/Articles/
```

By default the `my_account` cookie row is used (the same name from `add_cookie`
above). Use `--account` to pick a different row and `--out` to set the output
directory.

## Python API

```python
import asyncio
from pathlib import Path
from twscrape.articles import (
    Article,
    cookies_from_twscrape_db,
    extract,
    render_html,
    render_markdown,
)


async def main():
    cookies = cookies_from_twscrape_db("./accounts.db", account="my_account")

    article: Article = await extract(
        "https://x.com/thedankoe/status/2010751592346030461?s=20",
        cookies,
    )

    print(article.title)        # "How to fix your entire life in 1 day"
    print(article.word_count)   # 5556
    print(article.image_count)  # 3
    print(article.video_count)  # 0

    Path("./out.html").write_text(render_html(article))
    Path("./out.md").write_text(render_markdown(article))

    for block in article.blocks:
        if block.kind == "image":
            print(block.image.src)


asyncio.run(main())
```

## How article extraction works

1. Load `auth_token` + `ct0` from your accounts DB (or `cookies_from_dict({...})`).
2. Launch headless Chromium with those cookies.
3. Navigate to the article URL (`/i/article/{id}` or
   `/<user>/article/<tweet_id>`).
4. Wait for `[data-testid="twitterArticleReadView"]`.
5. Run a `TreeWalker` that accepts `<h2>`, `<h3>`, `<blockquote>`,
   `<ul>/<ol>`, `<img>`, `<video>`, and **both** `<p>` and
   `.public-DraftStyleDefault-block` (X's Draft.js format coexists with `<p>`
   on the same page). Subtrees inside `<li>/<ul>/<ol>/<blockquote>/<figure>/
   <h2>/<h3>/<header>/<footer>` are `FILTER_REJECT`ed so they aren't
   re-emitted as duplicate paragraphs.
6. Emit blocks in document order, preserving text / image / video interleaving.
7. Render to HTML (default) or Markdown.

**Why HTML is the default:** it embeds images natively (with captions and
responsive sizing), renders offline via self-contained CSS, and turns videos
into clickable poster cards. Markdown is the plain-text-friendly fallback for
notes apps, diffs, and version control. Both renderers preserve the same
heading hierarchy, paragraph breaks, blockquotes, and lists.

## Architecture

```
twitter-x-content_DL/
├── twscrape/
│   ├── api.py              # GraphQL scraping API (upstream)
│   ├── cli.py              # `twitter-x-content_DL` dispatcher (+ `article` subcommand)
│   ├── models.py           # Tweet / User / Media (upstream)
│   └── articles/           # NEW
│       ├── __init__.py     # public API surface
│       ├── models.py       # Article / ArticleBlock / ArticleAuthor
│       ├── extractor.py    # Playwright renderer + TreeWalker
│       └── renderers.py    # HTML + Markdown
├── tests/articles/         # NEW — renderer + safe_filename unit tests, extractor smoke test
├── pyproject.toml
├── readme.md
├── LICENSE                 # MIT (vladkens 2023 + Francis Kwan 2026)
└── changelog.md
```

## Tests

```bash
uv run pytest tests/articles/test_articles.py            # 47 deterministic unit tests (~0.1s)
uv run pytest tests/articles/test_extractor.py -v        # live smoke test (skips without creds)
```

Unit tests cover renderers, `safe_filename`, model serialization, cookie
helpers, and URL parsing. The integration test extracts a live article (~14s)
and auto-skips when cookies or Playwright are unavailable.

## License

MIT — see [LICENSE](LICENSE).

```
Copyright (c) 2023 vladkens
Copyright (c) 2026 Francis Kwan
```

Upstream `twscrape` code (everything outside `twscrape/articles/`) is preserved
under vladkens' MIT terms; the new article module is also MIT.

## Credits

- [vladkens/twscrape](https://github.com/vladkens/twscrape) — original GraphQL
  scraping library.
- [Playwright](https://playwright.dev/python/) — headless browser engine for
  article rendering.

## X / Twitter Terms of Service

Scraping X must comply with their Terms of Service, robots.txt, and applicable
law. Unofficial methods (GraphQL endpoints, browser simulation) carry
account-suspension risk. Use responsibly — your own accounts, proxies, and rate
limiting. X's platform changes frequently, so this tool needs ongoing
maintenance.
