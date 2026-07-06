## v0.1.0 – 2026-07-06

Initial release of the `twitter-x-content_DL` fork.

### About this fork

This is a fork of [vladkens/twscrape](https://github.com/vladkens/twscrape)
v0.19.1, licensed under MIT. vladkens' original GraphQL scraping code is
preserved as-is. New work in this fork is the `twscrape/articles/`
subpackage plus the `article` CLI subcommand.

### Features added

- **Article extraction** — `twitter-x-content_DL article <url>` extracts
  any X long-form article (`https://x.com/<user>/article/<tweet_id>`)
  to a self-contained HTML file (default) or Markdown (`--md`). Preserves
  heading hierarchy (`<h2>` / `<h3>`), paragraphs, blockquotes, bullet /
  numbered lists, inline images, and video cards. Uses Playwright +
  TreeWalker on the SSR HTML of `/i/article/{id}` so the approach is
  hash-rotation-proof.
- **Python API for articles** — `await twscrape.articles.extract(url,
  cookies) -> Article` returns a structured `Article` dataclass with
  ordered blocks (heading / paragraph / image / video_card / list /
  blockquote). Render with `render_html(article)` or
  `render_markdown(article)`.
- **Filename convention** — output files use the article's canonical
  title (sanitized for filesystem safety), with the tweet id appended as
  a disambiguating suffix: `<safe_title>_<id>.html`.

### How articles are extracted

1. Load `auth_token` + `ct0` cookies from a twscrape accounts.db (or
   pass directly as `cookies_from_dict({...})`)
2. Launch headless Chromium with those cookies attached
3. Navigate to the article URL
4. Wait for `[data-testid="twitterArticleReadView"]` to render
5. Walk the DOM with a `TreeWalker` that accepts `<h2>`, `<h3>`,
   `<blockquote>`, `<ul>/<ol>`, `<img>`, `<video>`, `<p>`, AND
   `.public-DraftStyleDefault-block` (X's Draft.js editor format
   coexisting with `<p>`)
6. `FILTER_REJECT` (not skip) subtrees inside `<li>/<ul>/<ol>/
   <blockquote>/<figure>/<h2>/<h3>/<header>/<footer>` to avoid
   duplicate text emission
7. Render blocks in document order to HTML / Markdown

### Why this is a fork and not a PR upstream

X article bodies are NOT reachable via any stable GraphQL endpoint
(queryId hash rotates, direct probing yields 422 / 404). Headless
Chromium rendering is the only robust programmatic method, but it
requires Playwright (~150 MB browser download) — a new dependency
that doesn't fit upstream twscrape's lightweight GraphQL-only design.
Rather than block on upstream review, this fork ships the feature
under a new package name so anyone can `pip install
"twitter-x-content_DL[article]"` today.

### Tests

- 47 unit tests for renderers, `safe_filename`, model serialization,
  cookie helpers, URL parsing (deterministic, ~0.1s, no network)
- 2 integration tests for end-to-end extraction against a live article
  (~14s each, auto-skip if cookies or Playwright are unavailable)

### Upstream baseline

Forked from vladkens/twscrape **v0.19.1** (2026-06-26). All upstream
GraphQL methods, models, login flow, and CLI subcommands are preserved.
The only changes to upstream code are:

- `pyproject.toml` — package name, version, description, authors,
  entry-point, new `[article]` optional extra
- `twscrape/cli.py` — added `article` subparser + `_handle_article()`
  dispatcher
- `LICENSE` — combined MIT copyright (vladkens 2023 + Francis Kwan 2026)
- `readme.md` — replaced with fork-specific content

---

## v0.19.1 – 2026-06-26 (upstream baseline)