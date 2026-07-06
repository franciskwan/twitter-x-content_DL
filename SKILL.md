---
name: "twitter-x-content-dl-cli"
description: "Use the twitter-x-content_DL CLI to scrape X/Twitter content — articles, posts, threads, users, search. Triggers on 'extract X article', 'download X article', 'scrape X tweets', 'twitter/x data extraction', 'article body in HTML/Markdown', 'playwright x.com'."
tags: ["twitter", "x", "scraping", "articles", "playwright"]
---

# twitter-x-content_DL — Skill

A guide for LLMs / agents on how to invoke the `twitter-x-content_DL` CLI
to extract X / Twitter content. Forked from
[vladkens/twscrape](https://github.com/vladkens/twscrape); adds Playwright
article extraction.

## When to use

Trigger on any of:

- "extract / download / scrape an X article"
- "article body in HTML or Markdown"
- "playwright x.com"
- "twitter data extraction"
- "scrape X tweets / threads"
- "X API without official API key"

If the user only needs GraphQL scraping (search, tweets, users), the
`twscrape` upstream CLI commands work as-is. Article extraction is the new
capability unique to this fork.

## Install

```bash
# Core (GraphQL scraping) — lightweight
pip install twitter-x-content_DL

# Article extraction — adds Playwright + Chromium (~150 MB)
pip install "twitter-x-content_DL[article]"
python -m playwright install chromium
```

## Set up auth (once)

The CLI needs X cookies (`auth_token` + `ct0`) for both GraphQL and
article extraction. To get them: open x.com in a browser → DevTools (F12)
→ Application → Cookies → copy the values.

```bash
twitter-x-content_DL add_cookie my_account "auth_token=xxx; ct0=yyy"
```

Cookies are stored in `accounts.db` (default) — point with `--db`.

## Common commands

### Extract a single article (default HTML)

```bash
twitter-x-content_DL article "https://x.com/<user>/status/<tweet_id>"
```

Output: writes `./<safe_title>_<id>.html` in the current directory.

### Markdown instead of HTML

```bash
twitter-x-content_DL article "https://x.com/<user>/article/<tweet_id>" --md
```

### Custom output directory

```bash
twitter-x-content_DL article "<url>" --out ~/Documents/Articles/
```

### Pick a different account row from --db

```bash
twitter-x-content_DL --db ./accounts.db article "<url>" --account backup_account
```

### Search tweets (GraphQL — upstream twscrape)

```bash
twitter-x-content_DL search "from:xdevelopers lang:en" --limit=20
```

### Get a tweet + its thread

```bash
twitter-x-content_DL tweet_details 1701694747767648500
twitter-x-content_DL tweet_thread 1701694747767648500
```

### User profile + tweets

```bash
twitter-x-content_DL user_by_login xdevelopers
twitter-x-content_DL user_tweets 1632207375288254464 --limit=10
```

## Programmatic (Python)

For batch jobs (e.g. processing 100 bookmarks):

```python
import asyncio
from pathlib import Path
from twscrape.articles import (
    Article,
    cookies_from_twscrape_db,
    extract,
    render_html,
    render_markdown,
    safe_filename,
)


async def extract_all(urls: list[str], db_path: str, out_dir: str):
    cookies = cookies_from_twscrape_db(db_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    for url in urls:
        article = await extract(url, cookies)
        slug = safe_filename(article.title or "untitled")
        ext = "html"  # or "md"
        (out / f"{slug}_{article.url.rsplit('/', 1)[-1].split('?')[0]}.{ext}") \
            .write_text(render_html(article))


asyncio.run(extract_all(
    ["https://x.com/foo/status/123", "https://x.com/bar/status/456"],
    db_path="./accounts.db",
    out_dir="./articles/",
))
```

## Pitfalls

**Don't try GraphQL for article bodies.** The `ArticleEntityByRestId`
queryId hash rotates; direct probing yields 422 / 404. The robust method
is headless Chromium rendering, which is what `twitter-x-content_DL
article` does. Trying GraphQL first wastes ~30 min (learned this the hard
way — see the project README's "Why headless Chromium" section).

**Don't trust the `logged_in = 0` flag in `accounts` table for cookie-only
accounts.** That's cosmetic — the cookies themselves are fully valid;
verify auth with a real API call, not the table display.

**The `[article]` extra requires Playwright + Chromium download.** If
`pip install` is done without `[article]`, the `article` subcommand will
fail with a clear "Playwright is required" error. Re-run with the extra
and `python -m playwright install chromium`.

**Video blocks become clickable cards, not embedded videos.** X serves
article-embedded videos via session-scoped `blob:` URLs that don't survive
extraction. The renderer emits an `<a class="video-card">` linking back to
the source tweet so the user can play it in the real X client.

## Reference

- Project README: <https://github.com/franciskwan/twitter-x-content_DL#readme>
- Upstream twscrape: <https://github.com/vladkens/twscrape>
- Playwright Python: <https://playwright.dev/python/>