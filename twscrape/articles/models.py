"""Article extraction models.

Adds dataclasses that represent an X / Twitter long-form article: title,
author, source URL, and an ordered list of content blocks (headings,
paragraphs, images, videos, lists, blockquotes).

These mirror the upstream twscrape style (dataclasses + JSONTrait) so the
public surface is consistent with `Tweet`, `User`, `Media`, etc.
"""

from dataclasses import dataclass, field

from ..models import JSONTrait

# Block kinds — kept as constants instead of an enum so JSON output stays
# plain strings (matches how upstream exposes other kinds of "kind" fields).
BLOCK_HEADING = "heading"
BLOCK_PARAGRAPH = "paragraph"
BLOCK_IMAGE = "image"
BLOCK_VIDEO_CARD = "video_card"
BLOCK_LIST = "list"
BLOCK_BLOCKQUOTE = "blockquote"


@dataclass
class ArticleAuthor(JSONTrait):
    """The author of an article.

    All fields are optional because not every X article page exposes the
    full author metadata in the SSR HTML — the byline is usually enough.
    """

    username: str | None = None
    display_name: str | None = None
    profile_image_url: str | None = None
    profile_url: str | None = None


@dataclass
class ArticleImage(JSONTrait):
    """An image embedded in the article body.

    Captured from the article reader's rendered DOM. URLs come from X's
    `pbs.twimg.com/media/...` CDN.
    """

    src: str
    alt: str = ""
    width: int | None = None
    height: int | None = None


@dataclass
class ArticleVideoCard(JSONTrait):
    """A placeholder for an embedded video.

    X serves article-embedded videos via session-scoped `blob:` URLs that
    don't survive extraction. We can't embed the video directly; instead we
    emit a clickable card linking back to the source tweet so the user can
    play it in the real X client.
    """

    tweet_url: str
    poster_url: str = ""
    # The raw blob: URL if it was present at extraction time (always empty in
    # the rendered output because blob URLs are session-scoped).
    src: str = ""


@dataclass
class ArticleList(JSONTrait):
    """An ordered or unordered list."""

    items: list[str]
    ordered: bool = False


@dataclass
class ArticleBlock(JSONTrait):
    """A single content block in the article, in document order.

    `kind` is one of BLOCK_* constants. Exactly one of the content fields
    is populated per block; the rest are None / empty.
    """

    kind: str
    text: str | None = None
    level: int | None = None  # heading level (2 or 3) — only for BLOCK_HEADING
    image: ArticleImage | None = None
    video_card: ArticleVideoCard | None = None
    list: ArticleList | None = None


@dataclass
class Article(JSONTrait):
    """A complete X article.

    `blocks` is ordered to preserve the original article's reading flow
    (paragraph interleaved with images / video cards / lists).
    """

    title: str
    url: str
    author: ArticleAuthor | None = None
    blocks: list[ArticleBlock] = field(default_factory=list)
    # Convenience accessor — joined plain text of all paragraph / heading /
    # blockquote / list blocks. Useful for full-text search / word counts.
    body_text: str = ""

    @property
    def word_count(self) -> int:
        if not self.body_text:
            return 0
        # CJK-friendly: count CJK chars individually, then split on
        # whitespace for the rest. Good enough for a display metric.
        cjk = sum(1 for c in self.body_text if "\u4e00" <= c <= "\u9fff")
        other = len([w for w in self.body_text.split() if w])
        return cjk + other

    @property
    def image_count(self) -> int:
        return sum(1 for b in self.blocks if b.kind == BLOCK_IMAGE)

    @property
    def video_count(self) -> int:
        return sum(1 for b in self.blocks if b.kind == BLOCK_VIDEO_CARD)
