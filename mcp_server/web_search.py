from __future__ import annotations

import asyncio
import logging
import os
import re
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx
from ddgs import DDGS
from ddgs.exceptions import (
    DDGSException,
    RatelimitException,
    TimeoutException,
)


logger = logging.getLogger(__name__)

# Content budget is spread evenly across results: a single total cap starved
# the most relevant pages, which are often not the first ones DuckDuckGo
# returns (ads and generic portals usually come first).
_MAX_CONTENT_LENGTH = 1500
_MAX_TOTAL_CONTENT_LENGTH = 7500
_MAX_FETCHED_PAGES = 6
_HTTP_TIMEOUT = 10.0

# Search engines are tried in this order. "auto" must not be used: ddgs falls
# back to any engine that happens to answer, and the yandex engine returns
# unrelated spam for most queries, which the model then treats as real results.
_SEARCH_BACKENDS = ("duckduckgo", "bing", "brave", "mojeek")

# ddgs defaults to us-en, which returns US-only results for Russian queries.
_SEARCH_REGION = os.getenv("SEARCH_REGION", "ru-ru")


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
    """Search the web, trying each engine in turn until one answers.

    ddgs' own multi-engine mode is not used on purpose: it batches engines by
    ceil(max_results / 10) + 1 workers and collects only the futures that
    already finished, so results from the slow engine get dropped. It also
    defaults to region "us-en", and its "yandex" engine answers most queries
    with unrelated spam.

    Engines are tried individually because they block each other
    independently: while one is rate limited the next usually still works.
    Only once every engine has failed do we back off and retry the round.
    """
    import random

    kwargs.setdefault("region", _SEARCH_REGION)
    last_error = ""

    for attempt in range(3):
        for backend in _SEARCH_BACKENDS:
            try:
                with DDGS() as ddgs:
                    fn = getattr(ddgs, method)
                    result = fn(query, backend=backend, **kwargs)
                if result:
                    return list(result)
                last_error = f"{backend}: пусто"
            except (RatelimitException, TimeoutException) as exc:
                last_error = f"{backend}: {str(exc)[:60]}"
                logger.debug("engine %s unavailable: %s", backend, last_error)
            except DDGSException as exc:
                last_error = f"{backend}: {str(exc)[:60]}"
                logger.debug("engine %s returned nothing: %s", backend, last_error)
            except Exception as exc:
                last_error = f"{backend}: {str(exc)[:60]}"
                logger.debug("engine %s failed: %s", backend, last_error)

        if attempt < 2:
            wait = 3 ** (attempt + 1) + random.uniform(0, 1.5)
            logger.warning("all search engines failed (attempt %d, last: %s), retrying in %.1fs",
                           attempt + 1, last_error, wait)
            await asyncio.sleep(wait)

    logger.error("search failed after all attempts, last error: %s", last_error)
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
    """Search the web and fetch page content for the top results."""
    query = (query or "").strip()
    if not query:
        return [{
            "title": "", "url": "",
            "snippet": "Пустой поисковый запрос. Уточни, что именно нужно найти.",
        }]

    raw = await _safe_ddgs_call("text", query, max_results=max_results)

    if not raw:
        return [{
            "title": "",
            "url": "",
            "snippet": (
                f"Поиск по запросу «{query}» не вернул результатов. "
                "Попробуй переформулировать запрос или задать его иначе."
            ),
        }]

    urls: list[str] = []
    for r in raw:
        url = r.get("href", "")
        if _should_fetch(url):
            urls.append(url)

    # Fetch more pages than we can afford to include: a relevant page often
    # sits below ads and generic portals that return nothing useful.
    fetch_targets = urls[:_MAX_FETCHED_PAGES]

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
        fetched = await asyncio.gather(*(_fetch_page(client, u) for u in fetch_targets),
                                       return_exceptions=True)
    content_by_url = {
        url: ("" if isinstance(content, BaseException) else content)
        for url, content in zip(fetch_targets, fetched)
    }

    per_result_cap = max(
        400, _MAX_TOTAL_CONTENT_LENGTH // max(len(raw), 1)
    )
    per_result_cap = min(per_result_cap, _MAX_CONTENT_LENGTH)

    results: list[dict[str, str]] = []
    budget = _MAX_TOTAL_CONTENT_LENGTH
    for r in raw:
        url = r.get("href", "")
        item: dict[str, str] = {
            "title": r.get("title", ""),
            "url": url,
            "snippet": r.get("body", ""),
        }
        content = content_by_url.get(url) or ""
        if content and budget > 0:
            allowance = min(per_result_cap, budget)
            item["content"] = content[:allowance]
            budget -= len(item["content"])
        results.append(item)

    return results


async def search_images(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Search for images using Wikimedia Commons API (free, no key needed)."""
    from urllib.parse import quote

    headers = {"User-Agent": "Chat-UI/1.0 (https://github.com/Gerondiz/Chat-UI; chatbot)"}

    search_url = (
        "https://commons.wikimedia.org/w/api.php"
        "?action=query"
        "&list=search"
        f"&srsearch={quote(query)}"
        "&srnamespace=6"
        "&format=json"
        f"&srlimit={max_results}"
    )

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, headers=headers) as client:
            resp = await client.get(search_url)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.error("Wikimedia search failed: %s", exc)
        return []

    titles = [s["title"] for s in data.get("query", {}).get("search", [])]
    if not titles:
        return []

    # Batch fetch image info
    info_url = (
        "https://commons.wikimedia.org/w/api.php"
        "?action=query"
        f"&titles={'|'.join(quote(t) for t in titles)}"
        "&prop=imageinfo"
        "&iiprop=url|dimensions|mime"
        "&format=json"
    )

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, headers=headers) as client:
            resp = await client.get(info_url)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.error("Wikimedia image info failed: %s", exc)
        return []

    results: list[dict[str, str]] = []
    for pid, page in data.get("query", {}).get("pages", {}).items():
        if pid == "-1":
            continue
        ii = (page.get("imageinfo") or [{}])[0]
        url_val = ii.get("url", "")
        if not url_val:
            continue
        results.append({
            "title": page.get("title", query).replace("File:", "", 1),
            "image_url": url_val,
            "source_url": ii.get("descriptionurl", ""),
            "thumbnail": ii.get("thumburl", url_val),
        })
        if len(results) >= max_results:
            break

    return results
