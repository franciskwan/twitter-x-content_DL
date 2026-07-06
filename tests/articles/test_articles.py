"""Tests for the article extraction helpers.

Renderer + safe_filename tests are deterministic (no Playwright, no network).
The extractor is exercised by an integration smoke test in
`test_extractor.py` that requires real cookies + Playwright installed; it
auto-skips if those aren't available so CI on a clean checkout still passes.
"""

import pytest

from twscrape.articles import (
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
    render_html,
    render_markdown,
    safe_filename,
)
from twscrape.articles.renderers import _html_escape

# ---------------------------------------------------------------------------
# safe_filename
# ---------------------------------------------------------------------------


class TestSafeFilename:
    @pytest.mark.parametrize("inp,expected", [
        ("Hello World", "Hello World"),
        ("How To Pull Psychological Levers", "How To Pull Psychological Levers"),
        ('A/B test: "hello" / world? *', "A_B test_ _hello_ _ world"),
        ("   ...  leading & trailing   ...   ", "leading & trailing"),
        ("", "article"),
        ("   ", "article"),
        ("////", "article"),  # all-underscore result also falls back
    ])
    def test_basic_replacements(self, inp, expected):
        assert safe_filename(inp) == expected

    def test_max_len_cap_breaks_on_first_space(self):
        s = "x" * 50 + " " + "y" * 50 + " " + "z" * 50
        out = safe_filename(s, max_len=80)
        assert len(out) <= 80
        # rfind(" ", 0, 80) returns 50 (the first space) -> cut to 50 chars
        assert out == "x" * 50

    def test_max_len_cap_uses_later_space(self):
        # Space at index 80 — picked because it's the latest space within max_len
        s = "x" * 80 + " " + "y" * 50
        out = safe_filename(s, max_len=100)
        # cut = 80 (the space index), so s[:80] = "x"*80. Space itself is dropped.
        assert out == "x" * 80

    def test_max_len_cap_without_space(self):
        s = "x" * 200
        out = safe_filename(s, max_len=120)
        assert len(out) == 120  # no break point => hard cut

    def test_cjk_preserved(self):
        assert safe_filename("普通人如何成为一名量化交易员") == "普通人如何成为一名量化交易员"
        assert safe_filename("AI 循环：Claude") == "AI 循环：Claude"  # fullwidth colon kept

    def test_emoji_preserved(self):
        assert safe_filename("Hello 🚀 World") == "Hello 🚀 World"


# ---------------------------------------------------------------------------
# _html_escape
# ---------------------------------------------------------------------------


class TestHtmlEscape:
    def test_ampersand_first(self):
        # Must replace & FIRST so we don't double-escape other entities.
        assert _html_escape("a & b &amp; c") == "a &amp; b &amp;amp; c"

    def test_angle_brackets(self):
        assert _html_escape("<script>") == "&lt;script&gt;"

    def test_quotes(self):
        assert _html_escape("she said \"hi\"") == "she said &quot;hi&quot;"
        assert _html_escape("don't") == "don&#39;t"


# ---------------------------------------------------------------------------
# render_html
# ---------------------------------------------------------------------------


def _sample_article() -> Article:
    return Article(
        title="Test Article",
        url="https://x.com/example/status/123",
        author=ArticleAuthor(username="example", display_name="Example User"),
        blocks=[
            ArticleBlock(kind=BLOCK_HEADING, level=2, text="Section One"),
            ArticleBlock(kind=BLOCK_PARAGRAPH, text="First paragraph."),
            ArticleBlock(kind=BLOCK_IMAGE, image=ArticleImage(
                src="https://pbs.twimg.com/media/abc?format=jpg", alt="a photo", width=800, height=600,
            )),
            ArticleBlock(kind=BLOCK_PARAGRAPH, text="Second paragraph."),
            ArticleBlock(kind=BLOCK_BLOCKQUOTE, text="A quoted thought."),
            ArticleBlock(kind=BLOCK_LIST, list=ArticleList(items=["one", "two", "three"], ordered=False)),
            ArticleBlock(kind=BLOCK_HEADING, level=3, text="Subsection"),
            ArticleBlock(kind=BLOCK_VIDEO_CARD, video_card=ArticleVideoCard(
                tweet_url="https://x.com/example/status/123", poster_url="https://pbs.twimg.com/media/poster.jpg",
            )),
        ],
        body_text="Section One First paragraph. Second paragraph. A quoted thought. one / two / three Subsection",
    )


class TestRenderHtml:
    def test_basic_structure(self):
        html = render_html(_sample_article())
        assert html.startswith("<!doctype html>")
        assert "<title>Test Article</title>" in html
        assert "<h1>Test Article</h1>" in html
        assert html.rstrip().endswith("</html>")

    def test_h2_and_h3_preserved(self):
        html = render_html(_sample_article())
        assert "<h2>Section One</h2>" in html
        assert "<h3>Subsection</h3>" in html

    def test_paragraph_preserved(self):
        html = render_html(_sample_article())
        assert "<p>First paragraph.</p>" in html
        assert "<p>Second paragraph.</p>" in html

    def test_image_preserved(self):
        html = render_html(_sample_article())
        assert '<img src="https://pbs.twimg.com/media/abc?format=jpg"' in html
        assert '<figcaption>a photo</figcaption>' in html

    def test_blockquote_preserved(self):
        html = render_html(_sample_article())
        assert "<blockquote>A quoted thought.</blockquote>" in html

    def test_unordered_list_preserved(self):
        html = render_html(_sample_article())
        assert "<ul>" in html
        assert "<li>one</li>" in html
        assert "<li>two</li>" in html
        assert "<li>three</li>" in html
        assert "</ul>" in html

    def test_video_card_preserved(self):
        html = render_html(_sample_article())
        assert '<a class="video-card"' in html
        assert "Watch video on X" in html

    def test_byline_uses_author(self):
        html = render_html(_sample_article())
        assert "Example User" in html
        assert "@example" in html

    def test_byline_fallback_without_author(self):
        a = Article(title="t", url="https://x.com/u/status/1", blocks=[])
        html = render_html(a)
        assert '<p class="byline">' in html
        assert "https://x.com/u/status/1" in html

    def test_html_escaping_in_text(self):
        a = Article(
            title="x < y & z > w",
            url="https://x.com/u/status/1",
            blocks=[ArticleBlock(kind=BLOCK_PARAGRAPH, text="<script>alert('x')</script>")],
        )
        html = render_html(a)
        assert "&lt;script&gt;" in html
        assert "<script>" not in html.replace("<script>", "KEEPER", 1)  # only the first <script> is OK (style)

    def test_heading_level_clamped(self):
        a = Article(title="t", url="x", blocks=[
            ArticleBlock(kind=BLOCK_HEADING, level=99, text="deep"),
        ])
        html = render_html(a)
        assert "<h6>deep</h6>" in html


# ---------------------------------------------------------------------------
# render_markdown
# ---------------------------------------------------------------------------


class TestRenderMarkdown:
    def test_headings_preserved(self):
        md = render_markdown(_sample_article())
        # Markdown bumps h2 -> "##", h3 -> "###" (because article title uses "#")
        assert "## Section One" in md
        assert "### Subsection" in md

    def test_paragraphs_preserved(self):
        md = render_markdown(_sample_article())
        assert "First paragraph." in md
        assert "Second paragraph." in md

    def test_image_markdown_syntax(self):
        md = render_markdown(_sample_article())
        assert "![a photo](https://pbs.twimg.com/media/abc?format=jpg)" in md

    def test_blockquote_preserved(self):
        md = render_markdown(_sample_article())
        assert "> A quoted thought." in md

    def test_unordered_list_uses_dash(self):
        md = render_markdown(_sample_article())
        assert "- one" in md
        assert "- two" in md
        assert "- three" in md

    def test_video_card_as_link(self):
        md = render_markdown(_sample_article())
        assert "[Watch video on X](https://x.com/example/status/123)" in md

    def test_byline(self):
        md = render_markdown(_sample_article())
        assert "Example User" in md
        assert "@example" in md


# ---------------------------------------------------------------------------
# Article dataclass
# ---------------------------------------------------------------------------


class TestArticleDataclass:
    def test_image_count(self):
        a = Article(title="t", url="x", blocks=[
            ArticleBlock(kind=BLOCK_IMAGE, image=ArticleImage(src="a")),
            ArticleBlock(kind=BLOCK_IMAGE, image=ArticleImage(src="b")),
            ArticleBlock(kind=BLOCK_PARAGRAPH, text="p"),
        ])
        assert a.image_count == 2

    def test_video_count(self):
        a = Article(title="t", url="x", blocks=[
            ArticleBlock(kind=BLOCK_VIDEO_CARD, video_card=ArticleVideoCard(tweet_url="t")),
        ])
        assert a.video_count == 1

    def test_word_count_cjk_aware(self):
        a = Article(title="t", url="x", body_text="普通人 如何 成为 量化 交易员", blocks=[])
        # 12 CJK chars (普通人=3, 如何=2, 成为=2, 量化=2, 交易员=3) + 5 whitespace-split words
        assert a.word_count == 17

    def test_word_count_english(self):
        a = Article(title="t", url="x", body_text="the quick brown fox", blocks=[])
        assert a.word_count == 4

    def test_word_count_mixed(self):
        a = Article(title="t", url="x", body_text="hello 世界 world", blocks=[])
        # 2 CJK (世界) + 3 whitespace-split words (hello, 世界, world) = 5
        assert a.word_count == 5

    def test_word_count_empty(self):
        a = Article(title="t", url="x", body_text="", blocks=[])
        assert a.word_count == 0

    def test_json_serialization_roundtrip(self):
        a = _sample_article()
        js = a.json()
        # dataclasses.asdict → json.dumps round-trip; just verify it parses
        import json as _json
        parsed = _json.loads(js)
        assert parsed["title"] == "Test Article"
        assert len(parsed["blocks"]) == len(a.blocks)


# ---------------------------------------------------------------------------
# Cookie helpers
# ---------------------------------------------------------------------------


class TestCookieHelpers:
    def test_cookies_from_dict(self):
        from twscrape.articles import cookies_from_dict
        cookies = cookies_from_dict({"auth_token": "x", "ct0": "y"})
        assert len(cookies) == 2
        names = sorted(c.name for c in cookies)
        assert names == ["auth_token", "ct0"]
        for c in cookies:
            assert c.domain == ".x.com"
            assert c.path == "/"

    def test_cookies_from_dict_custom_domain(self):
        from twscrape.articles import cookies_from_dict
        cookies = cookies_from_dict({"k": "v"}, domain=".example.com")
        assert cookies[0].domain == ".example.com"


# ---------------------------------------------------------------------------
# article_id_from_url
# ---------------------------------------------------------------------------


class TestArticleIdFromUrl:
    @pytest.mark.parametrize("url,expected", [
        ("https://x.com/KKaWSB/article/2073914011524219109?s=20", "2073914011524219109"),
        ("https://x.com/i/article/2073912103778578432", "2073912103778578432"),
        ("https://x.com/KKaWSB/status/2073914011524219109?s=20", "2073914011524219109"),
        ("https://x.com/user/article/12345", "12345"),
    ])
    def test_extracts_numeric_id(self, url, expected):
        from twscrape.articles import article_id_from_url
        assert article_id_from_url(url) == expected

    def test_raises_on_garbage(self):
        from twscrape.articles import article_id_from_url
        with pytest.raises(ValueError):
            article_id_from_url("not a url")