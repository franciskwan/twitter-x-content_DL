"""Integration smoke test for the article extractor.

Requires:
- playwright installed and Chromium downloaded
- A twscrape accounts.db with a cookie-stored account row

Skipped automatically if either precondition isn't met, so CI on a clean
checkout still passes.

To run locally:
    cd twitter-x-content_DL
    uv pip install -e ".[article]"
    uv run python -m playwright install chromium
    uv run pytest tests/articles/test_extractor.py -v
"""

import sqlite3
from pathlib import Path

import pytest

# Skip everything if Playwright isn't installed
playwright = pytest.importorskip("playwright.async_api")

ACCOUNTS_DB = Path.home() / "tools/twscrape/accounts.db"
TEST_URL = "https://x.com/KKaWSB/article/2073914011524219109"


@pytest.fixture
def cookies():
    """Pull cookies from the local twscrape accounts.db if present."""
    if not ACCOUNTS_DB.exists():
        pytest.skip(f"no accounts.db at {ACCOUNTS_DB}")
    try:
        db = sqlite3.connect(ACCOUNTS_DB)
        row = db.execute(
            "SELECT cookies FROM accounts WHERE username = ?", ("my_account",)
        ).fetchone()
        if not row:
            pytest.skip(f"no `my_account` row in {ACCOUNTS_DB}")
    except Exception as e:
        pytest.skip(f"could not read {ACCOUNTS_DB}: {e}")

    import json as _json

    parsed = _json.loads(row[0])
    if "auth_token" not in parsed or "ct0" not in parsed:
        pytest.skip("auth_token / ct0 missing — login again first")

    from twscrape.articles import cookies_from_dict

    return cookies_from_dict(parsed)


@pytest.mark.asyncio
async def test_extract_real_article(cookies):
    """End-to-end against a live X article. ~10s wall-clock."""
    from twscrape.articles import extract

    article = await extract(TEST_URL, cookies, settle_ms=2000)
    assert article.title == "普通人如何成为一名量化交易员：一条被讲透的路径"
    assert article.url.startswith("https://x.com/KKaWSB/article/")
    assert len(article.blocks) > 5
    assert article.image_count >= 1
    assert article.word_count > 1000


@pytest.mark.asyncio
async def test_extract_returns_blocks_in_order(cookies):
    """The first block after the title should be either an image or a paragraph."""
    from twscrape.articles import BLOCK_HEADING, BLOCK_IMAGE, BLOCK_PARAGRAPH, extract

    article = await extract(TEST_URL, cookies, settle_ms=2000)
    assert len(article.blocks) > 0
    first_kind = article.blocks[0].kind
    assert first_kind in (BLOCK_IMAGE, BLOCK_PARAGRAPH, BLOCK_HEADING), (
        f"unexpected first block kind: {first_kind}"
    )
