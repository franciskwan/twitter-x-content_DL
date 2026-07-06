"""Render an Article to HTML or Markdown.

Both renderers preserve the article's original structure (h2 / h3 headings,
paragraphs, blockquotes, bullet / ordered lists) and interleave images /
video cards in document order.

HTML is the default — it can embed images natively, render the CSS for
readability (max-width, dark mode, system fonts including CJK fallbacks),
and surface video cards as clickable links back to the source tweet.

Markdown is provided as a fallback for users who want the content in a
plain-text-friendly format (e.g. pasting into a notes app, diffing, etc.).
Headings are preserved as `#` / `##` / `###`; images are emitted as
`![alt](src)`; video cards become a labelled link.
"""

import re

from .models import (
    BLOCK_BLOCKQUOTE,
    BLOCK_HEADING,
    BLOCK_IMAGE,
    BLOCK_LIST,
    BLOCK_PARAGRAPH,
    BLOCK_VIDEO_CARD,
    Article,
    ArticleBlock,
)

# ---------------------------------------------------------------------------
# Filesystem-safe filename helper
# ---------------------------------------------------------------------------

# Filesystem-unsafe across macOS/Windows/Linux + X-specific quote chars.
# Preserves CJK, accented Latin, emoji — only ASCII unsafe chars are substituted.
_UNSAFE_FN = re.compile(r'[\\/:\*\?"<>\|\x00-\x1f\x7f"\'`]')


def safe_filename(title: str, fallback: str = "article", max_len: int = 120) -> str:
    """Sanitize an article title for use as a markdown / html filename stem.

    Rules:
    - Replace filesystem-unsafe chars (\\ / : * ? " < > |, control bytes, quotes)
      with `_`.
    - Collapse runs of whitespace, trim leading/trailing whitespace and dots.
    - Cap at max_len chars, preferring to break on whitespace.
    - If the result is empty, fall back to `fallback`.
    """
    s = _UNSAFE_FN.sub("_", title or "")
    s = re.sub(r"\s+", " ", s).strip(" ._")
    # Treat "only delimiters left" as empty (e.g. "////" -> "____" -> "").
    if not s:
        return fallback
    if len(s) > max_len:
        cut = s.rfind(" ", 0, max_len)
        if cut < max_len * 0.6:
            cut = max_len
        s = s[:cut].rstrip(" .")
    return s


# ---------------------------------------------------------------------------
# HTML renderer
# ---------------------------------------------------------------------------

# Minimal self-contained stylesheet. No CDN, no @import — works offline once
# the user has the file. Tuned for reading long-form text comfortably.
_HTML_CSS = """\
:root { color-scheme: light dark; }
body { font: 17px/1.7 -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
       "Hiragino Sans GB", "Microsoft YaHei", sans-serif; max-width: 720px;
       margin: 40px auto; padding: 0 24px; color: #1a1a1a; background: #fdfdfd; }
@media (prefers-color-scheme: dark) {
  body { color: #e6e6e6; background: #15202b; }
  a { color: #1d9bf0; }
  blockquote { border-left-color: #38444d; color: #8b98a5; }
  hr { border-color: #38444d; }
  .byline { color: #8b98a5; }
}
h1 { font-size: 32px; line-height: 1.25; margin: 0 0 8px; letter-spacing: -0.01em; }
h2 { font-size: 24px; line-height: 1.3; margin: 36px 0 12px; letter-spacing: -0.005em; }
h3 { font-size: 20px; line-height: 1.4; margin: 28px 0 10px; }
p { margin: 0 0 16px; }
blockquote { margin: 16px 0; padding: 8px 16px; border-left: 4px solid #cfd9de;
             color: #536471; font-style: italic; }
hr { border: none; border-top: 1px solid #eff3f4; margin: 24px 0; }
a { color: #1d9bf0; text-decoration: none; }
a:hover { text-decoration: underline; }
.byline { font-size: 14px; color: #536471; margin: 4px 0 4px; }
.byline a { color: inherit; }
img { max-width: 100%; height: auto; display: block; margin: 16px auto;
      border-radius: 8px; }
figure { margin: 16px 0; }
figcaption { font-size: 13px; color: #8b98a5; text-align: center; margin-top: 4px; }
ul, ol { margin: 0 0 16px; padding-left: 28px; }
li { margin-bottom: 4px; }
.video-card { display: block; margin: 20px auto; max-width: 480px;
               border: 1px solid #cfd9de; border-radius: 12px; overflow: hidden;
               text-decoration: none; color: inherit; }
.video-card:hover { border-color: #1d9bf0; text-decoration: none; }
.video-card .poster { width: 100%; height: auto; display: block; background: #000; }
.video-card .label { padding: 12px 16px; font-size: 14px;
                     background: rgba(15, 20, 25, 0.03); }
@media (prefers-color-scheme: dark) {
  .video-card { border-color: #38444d; }
  .video-card:hover { border-color: #1d9bf0; }
  .video-card .label { background: rgba(255, 255, 255, 0.03); }
}
"""


def _html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def render_html(article: Article) -> str:
    """Render the article as a self-contained styled HTML file.

    Preserves:
    - h2 / h3 hierarchy (article structure)
    - paragraph ordering (text + images interleaved as in the original)
    - images (inline <img> with alt + caption)
    - videos (clickable card linking back to the tweet, with poster preview)
    - bullet / numbered lists (ul / ol)
    - blockquotes
    """
    title = (article.title or "Untitled").strip()
    url = article.url
    blocks = article.blocks

    out: list[str] = []
    out.append("<!doctype html>")
    out.append('<html lang="en">')
    out.append("<head>")
    out.append('<meta charset="utf-8">')
    out.append(f"<title>{_html_escape(title)}</title>")
    out.append(f'<meta name="x-article-source" content="{_html_escape(url)}">')
    out.append(f"<style>{_HTML_CSS}</style>")
    out.append("</head>")
    out.append("<body>")

    out.append(f"<h1>{_html_escape(title)}</h1>")

    # Author + source byline
    if article.author and (article.author.display_name or article.author.username):
        author = article.author
        author_label = author.display_name or author.username or ""
        author_handle = f"@{author.username}" if author.username else ""
        if author.profile_url:
            out.append(
                f'<p class="byline">{_html_escape(author_label)} '
                f'(<a href="{_html_escape(author.profile_url)}">{_html_escape(author_handle)}</a>) '
                f'— <a href="{_html_escape(url)}">Source on X</a></p>'
            )
        else:
            out.append(
                f'<p class="byline">{_html_escape(author_label)} '
                f'{_html_escape(author_handle)} — '
                f'<a href="{_html_escape(url)}">Source on X</a></p>'
            )
    else:
        out.append(
            f'<p class="byline">Source: <a href="{_html_escape(url)}">'
            f"{_html_escape(url)}</a></p>"
        )

    out.append("<hr>")

    for block in blocks:
        _emit_html_block(out, block)

    out.append("</body>")
    out.append("</html>")
    return "\n".join(out)


def _emit_html_block(out: list[str], block: ArticleBlock) -> None:
    kind = block.kind
    if kind == BLOCK_HEADING:
        level = max(2, min(6, int(block.level or 2)))  # clamp to 2..6
        out.append(f"<h{level}>{_html_escape(block.text or '')}</h{level}>")
    elif kind == BLOCK_PARAGRAPH:
        txt = _html_escape(block.text or "").replace("\n", "<br>")
        out.append(f"<p>{txt}</p>")
    elif kind == BLOCK_BLOCKQUOTE:
        txt = _html_escape(block.text or "").replace("\n", "<br>")
        out.append(f"<blockquote>{txt}</blockquote>")
    elif kind == BLOCK_LIST:
        if not block.list:
            return
        tag = "ol" if block.list.ordered else "ul"
        out.append(f"<{tag}>")
        for item in block.list.items:
            out.append(f"<li>{_html_escape(item)}</li>")
        out.append(f"</{tag}>")
    elif kind == BLOCK_IMAGE:
        if not block.image:
            return
        alt = _html_escape(block.image.alt) or "article image"
        src = _html_escape(block.image.src)
        out.append("<figure>")
        out.append(f'<img src="{src}" alt="{alt}" loading="lazy">')
        if block.image.alt:
            out.append(f"<figcaption>{alt}</figcaption>")
        out.append("</figure>")
    elif kind == BLOCK_VIDEO_CARD:
        if not block.video_card:
            return
        poster = _html_escape(block.video_card.poster_url)
        tweet_url = _html_escape(block.video_card.tweet_url or "")
        out.append(
            f'<a class="video-card" href="{tweet_url}" target="_blank" rel="noopener">'
        )
        if poster:
            out.append(
                f'<img class="poster" src="{poster}" alt="video poster" loading="lazy">'
            )
        else:
            out.append('<div class="poster" style="aspect-ratio:16/9;background:#000;"></div>')
        out.append('<div class="label">▶ Watch video on X (opens in new tab)</div>')
        out.append("</a>")


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------


def render_markdown(article: Article) -> str:
    """Render the article as Markdown.

    Preserves heading hierarchy (`#` / `##` / `###`), paragraph breaks,
    blockquotes (`> ...`), bullet (`- `) and ordered (`1. `) lists, images
    (`![alt](src)`), and video cards as labelled links.

    For users who need plain-text-friendly output (notes apps, diffs, etc.).
    """
    title = (article.title or "Untitled").strip()
    url = article.url

    out: list[str] = []
    out.append(f"# {title}")
    out.append("")

    if article.author and (article.author.display_name or article.author.username):
        author = article.author
        author_label = author.display_name or author.username or ""
        author_handle = f"@{author.username}" if author.username else ""
        out.append(
            f"> **{author_label}** {author_handle} — [Source on X]({url})"
        )
        out.append("")
    else:
        out.append(f"> Source: {url}")
        out.append("")

    out.append("---")
    out.append("")

    for block in article.blocks:
        _emit_markdown_block(out, block)

    return "\n".join(out)


def _emit_markdown_block(out: list[str], block: ArticleBlock) -> None:
    kind = block.kind
    if kind == BLOCK_HEADING:
        level = max(1, min(6, int(block.level or 2) + 0))  # h2 -> ##, h3 -> ###
        # In markdown we want h2 -> "##", h3 -> "###" (article title is "#"
        # already used at the top). Bump heading level by +1.
        md_level = min(6, level + 1)
        out.append("")
        out.append(f"{'#' * md_level} {block.text or ''}")
        out.append("")
    elif kind == BLOCK_PARAGRAPH:
        out.append(block.text or "")
        out.append("")
    elif kind == BLOCK_BLOCKQUOTE:
        for line in (block.text or "").split("\n"):
            out.append(f"> {line}")
        out.append("")
    elif kind == BLOCK_LIST:
        if not block.list:
            return
        for i, item in enumerate(block.list.items, start=1):
            prefix = f"{i}." if block.list.ordered else "-"
            out.append(f"{prefix} {item}")
        out.append("")
    elif kind == BLOCK_IMAGE:
        if not block.image:
            return
        alt = block.image.alt or "article image"
        src = block.image.src
        out.append(f"![{alt}]({src})")
        if block.image.alt:
            out.append(f"*{alt}*")
        out.append("")
    elif kind == BLOCK_VIDEO_CARD:
        if not block.video_card:
            return
        tweet = block.video_card.tweet_url or ""
        poster = block.video_card.poster_url
        if poster:
            out.append(f"[![Video poster]({poster})]({tweet})")
            out.append("")
        out.append(f"▶ **[Watch video on X]({tweet})**")
        out.append("")