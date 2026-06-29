import asyncio
from ddgs import DDGS
from cache_manager import get_cache

from dotenv import load_dotenv
load_dotenv()
import os

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
_has_tavily = bool(
    TAVILY_API_KEY
    and TAVILY_API_KEY.startswith("tvly-")
    and "替换" not in TAVILY_API_KEY
)


async def web_search(query: str, max_results: int = 5) -> str:
    """搜索网络信息，返回结果列表（含标题、摘要、来源链接）。
    适合用来回答用户的问题，并给出资料来源。"""

    cache_key = f"{query}|{max_results}"
    cache = get_cache()
    cached = await cache.get("search", cache_key)
    if cached is not None:
        return cached

    lines = []

    try:
        results = await asyncio.to_thread(_ddgs_search, query, max_results)
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}")
            lines.append(f"   摘要: {r['body']}")
            lines.append(f"   来源: {r['href']}")
            lines.append("")
    except Exception as e:
        lines.append(f"[DuckDuckGo 搜索出错: {e}]")

    if _has_tavily:
        try:
            from tavily import TavilyClient

            tavily_result = await asyncio.to_thread(_tavily_search, query, max_results)
            if tavily_result.get("results"):
                lines.append("--- Tavily 搜索结果 ---")
                for i, r in enumerate(tavily_result["results"], 1):
                    lines.append(f"{i}. {r.get('title', '无标题')}")
                    lines.append(f"   摘要: {r.get('content', '无内容')}")
                    lines.append(f"   来源: {r.get('url', '无链接')}")
                    lines.append("")
        except Exception as e:
            lines.append(f"[Tavily 搜索出错: {e}]")

    result = "\n".join(lines) if lines else "未找到相关结果。"
    await cache.set("search", cache_key, result, ttl=3600)
    return result


def _ddgs_search(query: str, max_results: int) -> list[dict]:
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append(r)
    return results


def _tavily_search(query: str, max_results: int) -> dict:
    from tavily import TavilyClient

    client = TavilyClient(api_key=TAVILY_API_KEY)
    return client.search(query, max_results=max_results)
