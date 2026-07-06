"""Article extraction for X / Twitter long-form articles.

Public API
----------
- `extract(url, cookies)`           — async, render the article and return an `Article`
- `Article`, `ArticleBlock`, ...     — structured dataclasses
- `render_html(article)`             — render to self-contained styled HTML
- `render_markdown(article)`         — render to markdown (preserves h1/h2/h3)
- `safe_filename(title)`             — sanitize a title for use as a filename
- `Cookie`, `cookies_from_dict`,     — helpers for passing auth into the browser
  `cookies_from_twscrape_db`
- `article_id_from_url(url)`         — extract numeric id from any X article URL

Article extraction is opt-in via the `[article]` pip extra so the core
twscrape package stays GraphQL-only and lightweight.

    pip install "twitter-x-content_DL[article]"
    python -m playwright install chromium
"""

# ruff: noqa: F401
from .extractor import (
    Cookie,
    ExtractResult,
    article_id_from_url,
    cookies_from_dict,
    cookies_from_twscrape_db,
    extract,
)
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
from .renderers import render_html, render_markdown, safe_filename
