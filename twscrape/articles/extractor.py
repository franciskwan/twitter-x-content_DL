"""Article extractor — Playwright-based headless renderer for X articles.

Why this exists
---------------
X article bodies are NOT reachable via any stable GraphQL endpoint. The
`ArticleEntityByRestId` queryId hash rotates periodically; direct probing
yields 422 ("Internal server error") or 404 ("Query not found"). X serves
the article body in the SSR HTML of `/i/article/{id}` and the JS bundle
just hydrates it for interactivity.

We render the page in headless Chromium with the user's own auth cookies
attached, then walk the rendered DOM with a TreeWalker that:
- Accepts block-level elements (h2, h3, p, blockquote, ul/ol, img, video)
- Also accepts `.public-DraftStyleDefault-block` divs (X's Draft.js
  paragraph format — coexists with `<p>` on the same page)
- Rejects (not skips) subtrees inside `<li>/<ul>/<ol>/<blockquote>/<figure>/
  <h2>/<h3>/<header>/<footer>` so list items / blockquotes don't get
  re-emitted as duplicate sibling paragraphs

This approach is hash-rotation-proof and works regardless of any X-side
GraphQL changes, because we run the same JS bundle X's own web app runs.
"""

import json
import re
import sqlite3
from dataclasses import dataclass

from ..models import JSONTrait
from .models import (
    BLOCK_BLOCKQUOTE,
    BLOCK_HEADING,
    BLOCK_IMAGE,
    BLOCK_LIST,
    BLOCK_PARAGRAPH,
    BLOCK_VIDEO_CARD,
    Article,
    ArticleAuthor,
    ArticleBlock,
    ArticleImage,
    ArticleList,
    ArticleVideoCard,
)

# ---------------------------------------------------------------------------
# Cookie loading
# ---------------------------------------------------------------------------


@dataclass
class Cookie(JSONTrait):
    """A single browser cookie, shaped for Playwright's `context.add_cookies()`."""

    name: str
    value: str
    domain: str = ".x.com"
    path: str = "/"
    httpOnly: bool = False
    secure: bool = True
    sameSite: str = "None"


def cookies_from_dict(d: dict, domain: str = ".x.com") -> list[Cookie]:
    """Convert a `{name: value}` dict into a list of `Cookie` objects."""
    return [Cookie(name=n, value=v, domain=domain) for n, v in d.items()]


def cookies_from_twscrape_db(db_path: str, account: str = "my_account") -> list[Cookie]:
    """Load cookies from a vladkens/twscrape-style accounts.db SQLite file.

    Schema: `SELECT cookies FROM accounts WHERE username = ?` returns a JSON
    dict `{auth_token: "...", ct0: "..."}`. Compatible with any other store
    that uses the same shape — see `cookies_from_dict`.
    """
    db = sqlite3.connect(db_path)
    row = db.execute("SELECT cookies FROM accounts WHERE username = ?", (account,)).fetchone()
    if not row:
        raise RuntimeError(f"no account {account!r} in {db_path}")
    return cookies_from_dict(json.loads(row[0]))


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------


# The JavaScript we run inside the article reader's page context. It walks
# the DOM with a TreeWalker and returns ordered semantic blocks as JSON.
#
# Verified against @KKaWSB (Chinese, 7 H2s + 95 paragraphs),
# @philhchen "Career advice in the age of AI", and @0xCodila "Loop Engineering"
# (6 H2s + 10 bullet lists + 8 blockquotes + 6 figures).
_EXTRACT_JS = """() => {
    const url = location.href;
    const cleanTitle = (t) => (t || '').trim()
        .replace(/^To view keyboard shortcuts, press question mark\\s*/i, '')
        .replace(/\\s*View keyboard shortcuts\\s*$/i, '')
        .trim();

    // Canonical title resolution. X serves several different title formats
    // depending on page state:
    //   - Article page:    "<title> / X"            (e.g. "How To ... / X")
    //   - Auth wall:       "(3) X" / "X"            (counts of unread + brand)
    //   - Not-found:       "Post / X"
    //   - Loading stub:    "X" / "X" (the tab title before hydration)
    // The dedicated testid="twitter-article-title" element is the most reliable
    // because document.title / og:title are unread-badge stubs on cookie-only
    // sessions.
    const stripSuffix = (t) => (t || '').replace(/\\s*[/|]\\s*X\\s*$/i, '').trim();
    const isStub = (t) => {
        if (!t) return true;
        const s = stripSuffix(t);
        return /^\\(?\\d+\\)?\\s*$/.test(s)
            || /^(X|Twitter|Post|Happening now)$/i.test(s)
            || s.length < 4;
    };
    const metaContent = (sel) => {
        const el = document.querySelector(sel);
        return el && el.content ? el.content.trim() : '';
    };

    let realTitle = '';
    const titleEl = document.querySelector('[data-testid="twitter-article-title"]');
    if (titleEl && titleEl.innerText) realTitle = cleanTitle(titleEl.innerText);
    if (!realTitle && !isStub(document.title)) realTitle = stripSuffix(document.title);
    if (!realTitle) realTitle = stripSuffix(metaContent('meta[property="og:title"]'));
    if (!realTitle) realTitle = stripSuffix(metaContent('meta[name="twitter:title"]'));
    if (!realTitle) {
        const headings = Array.from(document.querySelectorAll('h1, h2'));
        let best = '';
        for (const h of headings) {
            const t = cleanTitle(h.innerText);
            if (t.length < 10 || t.length > 200) continue;
            if (/keyboard shortcut/i.test(t)) continue;
            if (isStub(t)) continue;
            if (t.length > best.length) best = t;
        }
        realTitle = best;
    }

    // Author metadata from schema.org / page meta (best-effort, may be null)
    let author = null;
    const authorEl = document.querySelector('[itemprop="author"]');
    if (authorEl) {
        author = {
            username: (authorEl.querySelector('[itemprop="additionalName"]') || {}).content || '',
            display_name: (authorEl.querySelector('[itemprop="name"]') || {}).content || '',
            profile_url: (authorEl.querySelector('[itemprop="url"]') || {}).content || '',
            profile_image_url: (authorEl.querySelector('[itemprop="image"]') || {}).content || '',
        };
    }

    // Walk the article body in document order.
    const readView = document.querySelector('[data-testid="twitterArticleReadView"]');
    if (!readView) {
        return { url, title: realTitle, author, body_blocks: [] };
    }
    const titleRoot = document.querySelector('[data-testid="twitter-article-title"]');
    const chromeRe = /^(click to (subscribe|unfollow|follow|share|refresh)\\b|following$|followers$|more replies|upgrade to premium|want to publish your own article$|subscribe$|(\\d+(\\.\\d+)?[KM]?)$|load more|join the next|eden\\.so|https?:)/i;
    const isChromeText = (t) => {
        if (!t) return true;
        if (chromeRe.test(t)) return true;
        if (/keyboard shortcut/i.test(t)) return true;
        if (/^(DAN KOE|@[a-zA-Z0-9_]+|Click to Unfollow|join the next content)/i.test(t)) return true;
        if (/^Want to publish your own Article/i.test(t)) return true;
        return false;
    };
    const blockText = (el) => {
        return (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
    };
    const isParagraph = (n) => {
        const t = n.tagName.toLowerCase();
        return t === 'p' ||
            (t === 'div' && n.classList && n.classList.contains('public-DraftStyleDefault-block'));
    };

    // Walk with FILTER_REJECT (not FILTER_SKIP) so elements inside containers
    // (li, blockquote, figure, heading) don't get re-emitted as duplicate
    // sibling paragraphs.
    const walker = document.createTreeWalker(
        readView,
        NodeFilter.SHOW_ELEMENT,
        {
            acceptNode: (node) => {
                if (titleRoot && (node === titleRoot || titleRoot.contains(node))) {
                    return NodeFilter.FILTER_REJECT;
                }
                for (let anc = node.parentElement; anc && anc !== readView; anc = anc.parentElement) {
                    const t = anc.tagName.toLowerCase();
                    if (t === 'li' || t === 'ul' || t === 'ol' ||
                        t === 'blockquote' || t === 'figure' ||
                        t === 'h2' || t === 'h3' || t === 'header' || t === 'footer') {
                        return NodeFilter.FILTER_REJECT;
                    }
                }
                const tag = node.tagName.toLowerCase();
                if (tag === 'p') return NodeFilter.FILTER_ACCEPT;
                if (tag === 'div' &&
                    node.classList && node.classList.contains('public-DraftStyleDefault-block')) {
                    return NodeFilter.FILTER_ACCEPT;
                }
                if (['h2','h3','blockquote','ul','ol','img','video'].includes(tag)) {
                    return NodeFilter.FILTER_ACCEPT;
                }
                return NodeFilter.FILTER_SKIP;
            }
        }
    );

    const seenText = new Set();
    const blocks = [];
    let node;
    while ((node = walker.nextNode())) {
        const tag = node.tagName.toLowerCase();
        if (tag === 'img') {
            const w = node.naturalWidth || node.width || 0;
            const h = node.naturalHeight || node.height || 0;
            if (w > 0 && w < 100 && h > 0 && h < 100) continue;  // avatars + chrome
            if (!node.src || !/^https?:\\/\\//.test(node.src)) continue;
            blocks.push({ kind: 'image', src: node.src, alt: node.alt || '', width: w, height: h });
        } else if (tag === 'video') {
            const src = node.currentSrc || node.src || '';
            const poster = node.poster || '';
            blocks.push({ kind: 'video_card', src, poster, tweet_url: url });
        } else if (tag === 'h2' || tag === 'h3') {
            const t = blockText(node);
            if (!t || t.length < 2) continue;
            if (isChromeText(t)) continue;
            seenText.add(t);
            blocks.push({ kind: 'heading', level: parseInt(tag[1], 10), text: t });
        } else if (isParagraph(node)) {
            const t = blockText(node);
            if (!t || t.length < 4) continue;
            if (isChromeText(t)) continue;
            if (seenText.has(t)) continue;
            seenText.add(t);
            blocks.push({ kind: 'paragraph', text: t });
        } else if (tag === 'blockquote') {
            const t = blockText(node);
            if (!t || t.length < 4) continue;
            if (isChromeText(t)) continue;
            if (seenText.has(t)) continue;
            seenText.add(t);
            blocks.push({ kind: 'blockquote', text: t });
        } else if (tag === 'ul' || tag === 'ol') {
            const items = Array.from(node.querySelectorAll(':scope > li'))
                .map(li => blockText(li))
                .filter(t => t && t.length >= 2 && !isChromeText(t));
            if (items.length === 0) continue;
            blocks.push({ kind: 'list', ordered: tag === 'ol', items });
        }
    }

    // Detect X's video component if no <video> tag walked (player can render
    // as <div data-testid="videoPlayer"> without a <video> child).
    const videoPlayer = readView.querySelector('[data-testid="videoPlayer"]');
    if (videoPlayer && !blocks.some(b => b.kind === 'video_card')) {
        const posterDiv = videoPlayer.querySelector('[style*="background-image"]');
        const posterMatch = posterDiv && (posterDiv.getAttribute('style') || '').match(/url\\(["']?([^"')]+)/);
        blocks.push({
            kind: 'video_card', src: '',
            poster: posterMatch ? posterMatch[1] : '',
            tweet_url: url,
        });
    }

    return { url, title: realTitle, author, body_blocks: blocks };
}"""


@dataclass
class ExtractResult(JSONTrait):
    """The raw payload returned by the browser-side extractor JS.

    Kept as a separate model so callers that want lower-level access (e.g.
    to write their own renderer) don't have to depend on `Article`.
    """

    url: str
    title: str
    body_blocks: list[dict]
    author: dict | None = None


def article_id_from_url(url: str) -> str:
    """Extract the numeric article id from an X /article/ or /status/ URL.

    `https://x.com/KKaWSB/article/2073914011524219109` -> `2073914011524219109`
    `https://x.com/i/article/2073912103778578432`     -> `2073912103778578432`
    `https://x.com/KKaWSB/status/2073914011524219109` -> `2073914011524219109`
    """
    m = re.search(r"/(?:i/)?article/(\d+)|/status/(\d+)", url)
    if not m:
        raise ValueError(f"could not extract article / tweet id from URL: {url!r}")
    return m.group(1) or m.group(2)


async def extract(
    url: str,
    cookies: list[Cookie],
    *,
    headless: bool = True,
    user_agent: str | None = None,
    settle_ms: int = 2000,
    page_timeout_ms: int = 60_000,
    selector_timeout_ms: int = 20_000,
) -> Article:
    """Render the article URL in headless Chromium and return a structured Article.

    Parameters
    ----------
    url : str
        Any of: `https://x.com/<user>/article/<tweet_id>`,
                `https://x.com/i/article/<article_id>`,
                `https://x.com/<user>/status/<tweet_id>`.
    cookies : list[Cookie]
        Cookies to attach to the browser context. At minimum you need a valid
        X `auth_token` and `ct0` pair (cookie-only auth works).
    headless : bool, default True
        Set False to watch the browser in debug mode.
    user_agent : str, optional
        Override the default Chrome UA (useful if X starts fingerprinting).
    settle_ms : int, default 2000
        Extra wait after the article reader appears, before walking the DOM.
    page_timeout_ms / selector_timeout_ms : int
        Playwright timeout knobs.

    Returns
    -------
    Article
        Structured dataclass with title, author, ordered blocks, and
        a precomputed body_text (joined plain text).
    """
    try:
        from playwright.async_api import async_playwright  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError(
            "Playwright is required for article extraction. Install with:\n"
            '  pip install "twitter-x-content_DL[article]"\n'
            "  python -m playwright install chromium"
        ) from e

    ua = user_agent or (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=ua,
            viewport={"width": 1280, "height": 1600},
        )
        await context.add_cookies([c.__dict__ for c in cookies])  # ty: ignore[invalid-argument-type]
        page = await context.new_page()

        await page.goto(url, wait_until="domcontentloaded", timeout=page_timeout_ms)
        try:
            await page.wait_for_selector(
                '[data-testid="twitterArticleReadView"], '
                '[data-testid="articleBody"], article, [role="article"]',
                timeout=selector_timeout_ms,
            )
        except Exception:
            pass  # the JS below will report an empty body_blocks list
        await page.wait_for_timeout(settle_ms)

        raw = await page.evaluate(_EXTRACT_JS)
        await browser.close()

    return _result_to_article(raw)


def _result_to_article(raw: dict) -> Article:
    """Convert the raw JS payload into a structured Article."""
    blocks: list[ArticleBlock] = []
    body_parts: list[str] = []

    for b in raw.get("body_blocks", []):
        kind = b.get("kind")
        if kind == BLOCK_HEADING:
            text = b.get("text", "")
            blocks.append(
                ArticleBlock(
                    kind=BLOCK_HEADING,
                    text=text,
                    level=int(b.get("level", 2)),
                )
            )
            body_parts.append(text)
        elif kind == BLOCK_PARAGRAPH:
            text = b.get("text", "")
            blocks.append(ArticleBlock(kind=BLOCK_PARAGRAPH, text=text))
            body_parts.append(text)
        elif kind == BLOCK_BLOCKQUOTE:
            text = b.get("text", "")
            blocks.append(ArticleBlock(kind=BLOCK_BLOCKQUOTE, text=text))
            body_parts.append(text)
        elif kind == BLOCK_IMAGE:
            blocks.append(
                ArticleBlock(
                    kind=BLOCK_IMAGE,
                    image=ArticleImage(
                        src=b.get("src", ""),
                        alt=b.get("alt", ""),
                        width=b.get("width") or None,
                        height=b.get("height") or None,
                    ),
                )
            )
        elif kind == BLOCK_VIDEO_CARD:
            blocks.append(
                ArticleBlock(
                    kind=BLOCK_VIDEO_CARD,
                    video_card=ArticleVideoCard(
                        tweet_url=b.get("tweet_url", ""),
                        poster_url=b.get("poster", ""),
                        src=b.get("src", ""),
                    ),
                )
            )
        elif kind == BLOCK_LIST:
            items = b.get("items", [])
            blocks.append(
                ArticleBlock(
                    kind=BLOCK_LIST,
                    list=ArticleList(items=items, ordered=bool(b.get("ordered", False))),
                )
            )
            body_parts.append(" / ".join(items))

    author_dict = raw.get("author") or {}
    author = None
    if any(author_dict.get(k) for k in ("username", "display_name")):
        author = ArticleAuthor(
            username=author_dict.get("username") or None,
            display_name=author_dict.get("display_name") or None,
            profile_url=author_dict.get("profile_url") or None,
            profile_image_url=author_dict.get("profile_image_url") or None,
        )

    return Article(
        title=raw.get("title", "") or "Untitled",
        url=raw.get("url", ""),
        author=author,
        blocks=blocks,
        body_text="\n\n".join(body_parts),
    )
