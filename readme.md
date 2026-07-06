# twitter-x-content_DL

<div align="center">

[![license](https://badges.ws/pypi/l/twitter-x-content-dl)](LICENSE)
[![python](https://badges.ws/pypi/python/twitter-x-content-dl)](#)

</div>

Async Python library and CLI for scraping **X / Twitter** content — the
original [vladkens/twscrape](https://github.com/vladkens/twscrape) GraphQL
methods (search, tweets, threads, users, followers, …) plus **headless-Chromium
extraction of long-form articles** that aren't reachable via any stable
GraphQL endpoint.

Forked from [vladkens/twscrape](https://github.com/vladkens/twscrape) under
the MIT license. vladkens' scraping code is preserved as-is; the article
extraction module is new.

## Features

### Inherited from upstream twscrape

- Async / await API for running multiple scrapers concurrently
- Search and GraphQL X / Twitter API methods (`search`, `tweet_details`,
  `tweet_thread`, `user_by_login`, `followers`, `user_tweets`, …)
- Login flow with optional email verification code retrieval
- Cookie-based account setup
- Saved account sessions and per-account proxies
- Raw Twitter API responses and parsed SNScrape-compatible models
- Automatic account switching across rate-limited operations

### Added by this fork

- **`twitter-x-content_DL article <url>`** — extract any X long-form article
  (the `https://x.com/<user>/article/<tweet_id>` long-form editor format,
  *not* a regular tweet / thread) to a self-contained HTML file
  (default) or Markdown (`--md`)
- Preserves article structure: `<h2>` / `<h3>` headings, paragraphs,
  bullet / numbered lists, blockquotes, and inline images in document order
- Inline `<img>` tags for cover and in-article images (X's `pbs.twimg.com`
  CDN, full-resolution URLs)
- Video cards as clickable links back to the source tweet — X serves
  article-embedded videos via session-scoped `blob:` URLs that don't
  survive extraction; we detect the player and emit a card linking to the
  real tweet so the user can play it
- Filename convention: `<sanitized_title>_<article_id>.<ext>` — uses the
  article's canonical title, not the URL slug
- Async Python API for programmatic use:
  `await twscrape.articles.extract(url, cookies) -> Article`

## Why headless Chromium (not GraphQL) for articles

X article bodies (the long-form editor format used at
`https://x.com/<user>/article/<id>`) are **not reachable** via any stable
GraphQL endpoint:

- `tweet_details` only returns article metadata (`title`, `preview_text`,
  `cover_media`, `rest_id`)
- The body lives behind `ArticleEntityByRestId`, whose queryId hash
  **rotates periodically** — direct probing yields 422 or 404
- X serves the article body in the SSR HTML of `/i/article/{id}`; the JS
  bundle just hydrates it for interactivity

The robust method is to render the public page in headless Chromium with
your own `auth_token` + `ct0` cookies attached, then walk the rendered DOM
with a `TreeWalker` that preserves block ordering. This is
**hash-rotation-proof** because we run the same JS bundle X's own web app
runs.

## Install

```bash
# Core library (GraphQL scraping) — lightweight, no Playwright
pip install twitter-x-content_DL

# Article extraction — adds Playwright + Chromium browser (~150 MB download)
pip install "twitter-x-content_DL[article]"
python -m playwright install chromium
```

The `[article]` extra is optional so users who only need GraphQL scraping
don't pull in Playwright. Use `uv` if you prefer:

```bash
uv pip install "twitter-x-content_DL[article]"
uv run python -m playwright install chromium
```

For browser-like TLS fingerprinting on the GraphQL side, install the
optional `curl` backend:

```bash
pip install "twitter-x-content_DL[curl]"
TWS_HTTP_BACKEND=curl twitter-x-content_DL search "from:xdevelopers lang:en" --limit=20
```

## Quickstart — GraphQL scraping

```bash
# Add an account from browser cookies
twitter-x-content_DL add_cookie my_account "auth_token=xxx; ct0=yyy"

# Search tweets
twitter-x-content_DL search "from:xdevelopers lang:en" --limit=20

# Get a tweet + its thread
twitter-x-content_DL tweet_details 1701694747767648500
twitter-x-content_DL tweet_thread 1701694747767648500

# User profile + tweets
twitter-x-content_DL user_by_login xdevelopers
twitter-x-content_DL user_tweets 1632207375288254464 --limit=10
```

Cookie accounts that include `ct0` are activated immediately; no
`login_accounts` step is needed. To get cookies: open x.com → DevTools
(F12) → Application → Cookies → copy `auth_token` and `ct0` values.

## Quickstart — article extraction

```bash
# Default: render as a self-contained HTML file in the current directory
twitter-x-content_DL article "https://x.com/KKaWSB/status/2073914011524219109?s=20"

# Output:
# title:    普通人如何成为一名量化交易员：一条被讲透的路径
# url:      https://x.com/KKaWSB/status/2073914011524219109?s=20
# blocks:   102  (images: 1, videos: 0)
# words:    3855
# format:   html
# wrote 8,701 chars -> ./普通人如何成为一名量化交易员：一条被讲透的路径_2073914011524219109.html
```

By default the cookie row named `my_account` is used (matching upstream
`twitter-x-content_DL add_cookie my_account …`). Use `--account` to
choose a different row.

```bash
# Pick a different account row from --db
twitter-x-content_DL --db ./accounts.db article \
  "https://x.com/i/article/2073912103778578432" \
  --account backup_account

# Markdown output
twitter-x-content_DL article \
  "https://x.com/KKaWSB/article/2073914011524219109" \
  --md

# Custom output directory
twitter-x-content_DL article \
  "https://x.com/KKaWSB/status/2073914011524219109?s=20" \
  --out ~/Documents/Articles/
```

Both `--md` and the default HTML output use the article's canonical title
as the filename — so a feed of N articles produces files you can actually
browse by topic, not by cryptic URL slug.

## Python API

For programmatic use (e.g. processing hundreds of bookmarks):

```python
import asyncio
from twscrape import API
from twscrape.articles import (
    Article,
    cookies_from_twscrape_db,
    extract,
    render_html,
    render_markdown,
)


async def main():
    # Reuse an existing twscrape accounts.db
    cookies = cookies_from_twscrape_db("./accounts.db", account="my_account")

    article: Article = await extract(
        "https://x.com/KKaWSB/status/2073914011524219109?s=20",
        cookies,
    )

    print(article.title)        # "普通人如何成为一名量化交易员：一条被讲透的路径"
    print(article.author.username)  # "KKaWSB"
    print(article.word_count)   # 3855
    print(article.image_count)  # 1
    print(article.video_count)  # 0

    # Render to file
    Path("./out.html").write_text(render_html(article))
    Path("./out.md").write_text(render_markdown(article))

    # Or walk the structured blocks programmatically
    for block in article.blocks:
        if block.kind == "image":
            print(f"image at: {block.image.src}")
        elif block.kind == "heading":
            print(f"h{block.level}: {block.text}")


asyncio.run(main())
```

## Architecture

```
twitter-x-content_DL/
├── twscrape/                       # Python package
│   ├── api.py                      # GraphQL scraping API (from upstream)
│   ├── cli.py                      # `twitter-x-content_DL` CLI dispatcher
│   ├── models.py                   # Tweet / User / Media (from upstream)
│   ├── articles/                   # NEW: article extraction module
│   │   ├── __init__.py             # Public API surface
│   │   ├── models.py               # Article / ArticleBlock / ArticleAuthor / ...
│   │   ├── extractor.py            # Playwright headless renderer + TreeWalker
│   │   └── renderers.py            # HTML (default) + Markdown renderers
│   ├── ... (other upstream files: account, db, http, login, …)
├── tests/
│   ├── ... (upstream tests)
│   └── articles/                   # NEW
│       ├── test_articles.py        # Renderer + safe_filename unit tests (47)
│       └── test_extractor.py       # Integration smoke test (skips without creds)
├── pyproject.toml
├── readme.md                       # this file
├── LICENSE                         # MIT (vladkens 2023 + Francis Kwan 2026)
└── changelog.md
```

## Article extraction: how it works

1. Load `auth_token` + `ct0` cookies from your accounts DB (or pass them
   directly as `cookies_from_dict({...})`)
2. Launch headless Chromium with those cookies attached
3. Navigate to the article URL (`/i/article/{id}` or
   `/<user>/article/<tweet_id>`)
4. Wait for `[data-testid="twitterArticleReadView"]` to appear
5. Run a `TreeWalker` inside the page that:
   - Accepts `<h2>`, `<h3>`, `<blockquote>`, `<ul>/<ol>`, `<img>`, `<video>`
   - Accepts BOTH `<p>` and `.public-DraftStyleDefault-block` (X's Draft.js
     editor format — coexists with `<p>` on the same page)
   - `FILTER_REJECT`s elements inside `<li>/<ul>/<ol>/<blockquote>/<figure>/
     <h2>/<h3>/<header>/<footer>` so list items / blockquotes don't get
     re-emitted as duplicate sibling paragraphs
6. Emit the blocks in document order, preserving original text / image /
   video-card interleaving
7. Render to a self-contained HTML file (default) or Markdown

This is **hash-rotation-proof** — it works regardless of any X-side
GraphQL changes because we run the same JS bundle X's own web app runs.

## Why both HTML and Markdown

HTML is the default because:

- It can embed images natively (Markdown image syntax works but is
  bare-bones — no captions, no responsive sizing)
- Self-contained CSS means the file renders correctly offline
- Video cards become clickable links with poster previews

Markdown is provided as a fallback for users who want plain-text-friendly
output (notes apps, diffs, version control). Both renderers preserve
`<h2>` / `<h3>` headings, paragraph breaks, blockquotes, and bullet /
ordered lists.

## Tests

```bash
# Unit tests (deterministic, ~0.1s)
uv run pytest tests/articles/test_articles.py

# Integration smoke tests (require Playwright + accounts.db with valid cookies)
uv run pytest tests/articles/test_extractor.py -v
```

47 unit tests cover renderers, safe_filename, model serialization, cookie
helpers, and URL parsing. The integration test extracts a live KKaWSB
article (~14s wall-clock) and auto-skips if cookies or Playwright are not
available.

## License

MIT — see [LICENSE](LICENSE).

```
Copyright (c) 2023 vladkens
Copyright (c) 2026 Francis Kwan
```

The original twscrape code by vladkens is preserved under its MIT terms.
New article extraction code in `twscrape/articles/` is also MIT.

## Credits

- [vladkens/twscrape](https://github.com/vladkens/twscrape) — original
  GraphQL scraping library. All `twscrape/*.py` files outside the
  `twscrape/articles/` subdirectory are derived from vladkens' work.
- [Playwright](https://playwright.dev/python/) — headless browser engine
  used for article rendering.

## Sponsor

Original twscrape is sponsored by Swiftproxy residential proxies — see
[vladkens/twscrape readme](https://github.com/vladkens/twscrape#sponsor).

## X / Twitter's Terms of Service

Scraping X must comply with their Terms of Service, robots.txt, and
applicable laws. Many tools use unofficial methods like GraphQL endpoints
or browser simulation, which carry risks of account suspension or blocks.
Use responsibly, preferably with your own accounts, proxies, and rate
limiting. X's platform changes frequently, so tools require ongoing
maintenance.