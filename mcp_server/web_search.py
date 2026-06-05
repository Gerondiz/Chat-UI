from __future__ import annotations

from duckduckgo_search import DDGS


def search_web(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Search the web using DuckDuckGo."""
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=max_results))
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            }
            for r in results
        ]
