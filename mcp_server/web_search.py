from __future__ import annotations

import re
import logging
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx
from duckduckgo_search import DDGS


logger = logging.getLogger(__name__)

_MAX_CONTENT_LENGTH = 8000
_HTTP_TIMEOUT = 10.0


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._text: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip:
            stripped = data.strip()
            if stripped:
                self._text.append(stripped)

    @property
    def text(self) -> str:
        return "\n".join(self._text)


def _extract_text(html: str) -> str:
    extractor = _TextExtractor()
    try:
        extractor.feed(html)
    except Exception:
        pass
    text = extractor.text
    # Normalize whitespace: collapse multiple newlines/spaces
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _should_fetch(url: str) -> bool:
    parsed = urlparse(url)
    scheme = parsed.scheme or "http"
    if scheme not in ("http", "https"):
        return False
    host = parsed.hostname or ""
    # Skip known non-textual domains
    skip_domains = {"youtube.com", "youtu.be", "instagram.com", "facebook.com", "twitter.com", "x.com", "tiktok.com"}
    for sd in skip_domains:
        if host.endswith(sd):
            return False
    return True


async def _fetch_page(url: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if "text/html" not in content_type and "text/plain" not in content_type:
                return ""
            html = resp.text
            text = _extract_text(html)
            if len(text) > _MAX_CONTENT_LENGTH:
                text = text[:_MAX_CONTENT_LENGTH] + "\n\n[...truncated]"
            return text
    except Exception as exc:
        logger.debug("Failed to fetch %s: %s", url, exc)
        return ""


def search_web(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Search the web using DuckDuckGo and fetch page content."""
    with DDGS() as ddgs:
        raw = list(ddgs.text(query, max_results=max_results))

    import asyncio
    results: list[dict[str, str]] = []
    for r in raw:
        url = r.get("href", "")
        snippet = r.get("body", "")
        item: dict[str, str] = {
            "title": r.get("title", ""),
            "url": url,
            "snippet": snippet,
        }
        if _should_fetch(url):
            content = asyncio.run(_fetch_page(url))
            if content:
                item["content"] = content
        results.append(item)

    return results
