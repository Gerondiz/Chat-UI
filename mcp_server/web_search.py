from __future__ import annotations

import asyncio
import logging
import re
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
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _should_fetch(url: str) -> bool:
    parsed = urlparse(url)
    scheme = parsed.scheme or "http"
    if scheme not in ("http", "https"):
        return False
    host = parsed.hostname or ""
    skip_domains = {"youtube.com", "youtu.be", "instagram.com", "facebook.com", "twitter.com", "x.com", "tiktok.com"}
    for sd in skip_domains:
        if host.endswith(sd):
            return False
    return True


async def _fetch_page(client: httpx.AsyncClient, url: str) -> str:
    try:
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


async def _safe_ddgs_call(method: str, query: str, **kwargs):
    """Call DDGS method with retry on rate limit."""
    import random
    for attempt in range(5):
        try:
            with DDGS() as ddgs:
                fn = getattr(ddgs, method)
                result = fn(query, **kwargs)
                return list(result) if result else []
        except Exception as exc:
            if attempt < 4:
                wait = 2 ** (attempt + 1) + random.uniform(0, 1)
                logger.warning("DDGS %s failed (attempt %d), retrying in %.1fs...", method, attempt + 1, wait)
                await asyncio.sleep(wait)
            else:
                logger.error("DDGS %s failed after 5 attempts: %s", method, exc)
                return []
    return []


async def _validate_image_url(client: httpx.AsyncClient, url: str) -> str:
    """Check if URL returns a valid image. Returns validated URL or empty string."""
    try:
        resp = await client.head(url, timeout=5.0, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code >= 400:
            return ""
        ct = resp.headers.get("content-type", "")
        if ct.startswith("image/"):
            return url
        return ""
    except httpx.ConnectError:
        return ""
    except Exception:
        return url


async def search_web(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Search the web using DuckDuckGo and fetch page content."""
    raw = await _safe_ddgs_call("text", query, max_results=max_results)

    urls: list[str] = []
    for r in raw:
        url = r.get("href", "")
        if _should_fetch(url):
            urls.append(url)

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
        contents = await asyncio.gather(*(_fetch_page(client, u) for u in urls), return_exceptions=False)

    content_by_url = dict(zip(urls, contents))

    results: list[dict[str, str]] = []
    for r in raw:
        url = r.get("href", "")
        item: dict[str, str] = {
            "title": r.get("title", ""),
            "url": url,
            "snippet": r.get("body", ""),
        }
        content = content_by_url.get(url) or ""
        if content:
            item["content"] = content
        results.append(item)

    return results


async def search_images(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Search for images using DuckDuckGo. Validates URLs and falls back to thumbnails."""
    raw = await _safe_ddgs_call("images", query, max_results=max_results, region="wt-wt")

    candidates: list[dict[str, str]] = []
    for r in raw:
        candidates.append({
            "title": r.get("title", ""),
            "image_url": r.get("image", ""),
            "thumbnail": r.get("thumbnail", ""),
            "source_url": r.get("url", ""),
            "width": str(r.get("width", "")),
            "height": str(r.get("height", "")),
        })

    async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:
        checks = await asyncio.gather(
            *(_validate_image_url(client, c["image_url"]) for c in candidates),
            return_exceptions=True,
        )

    results: list[dict[str, str]] = []
    for i, c in enumerate(candidates):
        valid = isinstance(checks[i], str) and bool(checks[i])
        if not valid and c["thumbnail"]:
            c["image_url"] = c["thumbnail"]
            results.append(c)
            continue
        results.append(c)

    return results
