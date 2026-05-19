import logging
import asyncio
from typing import Any

logger = logging.getLogger(__name__)

_DDG_TIMEOUT_SECONDS = 8  # Max time to wait for web search before giving up

def _ddg_sync(query: str) -> list[dict[str, Any]]:
    """Synchronous wrapper for DuckDuckGo search."""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=3))
    except Exception as exc:
        logger.warning("DuckDuckGo search failed: %s", exc)
        return []

async def search_health_web(query: str) -> str | None:
    """
    Perform a live web search for health/hospital queries.
    Runs the synchronous DDG API inside an executor to keep FastAPI async loop non-blocking.
    Has an 8-second timeout to prevent blocking the voice turn.
    """
    logger.info("Performing live web search for: %s", query)
    try:
        loop = asyncio.get_running_loop()
        results = await asyncio.wait_for(
            loop.run_in_executor(None, _ddg_sync, query),
            timeout=_DDG_TIMEOUT_SECONDS,
        )
        
        if not results:
            return None
            
        formatted = ["--- LIVE WEB SEARCH RESULTS ---"]
        for i, r in enumerate(results, 1):
            formatted.append(f"[{i}] {r.get('title')} ({r.get('href')})")
            formatted.append(r.get('body', ''))
        formatted.append("--- END LIVE WEB SEARCH RESULTS ---")
        return "\n".join(formatted)
    except asyncio.TimeoutError:
        logger.warning("Web search timed out after %ss for query: %s", _DDG_TIMEOUT_SECONDS, query)
        return None
    except Exception as e:
        logger.error("Web search service error: %s", e)
        return None
