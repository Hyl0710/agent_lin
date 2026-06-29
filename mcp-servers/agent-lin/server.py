from fastmcp import FastMCP
from dotenv import load_dotenv

load_dotenv()

from search_engine import web_search
from image_tools import reverse_image_search
from web_fetcher import fetch_webpage
from downloader import download_file
from cache_manager import get_cache

mcp = FastMCP("agent-lin")

mcp.tool()(web_search)
mcp.tool()(reverse_image_search)
mcp.tool()(fetch_webpage)
mcp.tool()(download_file)


@mcp.tool()
async def cache_stats() -> str:
    """查看缓存统计：总条目数、占用空间、各命名空间详情。"""
    cache = get_cache()
    s = await cache.stats()
    lines = [
        f"总条目: {s['total_entries']}",
        f"占用空间: {s['size_mb']} MB",
        f"过期条目: {s['expired_entries']}",
        "",
        "按命名空间:",
    ]
    for ns in s["by_namespace"]:
        lines.append(f"  {ns['namespace']}: {ns['count']} 条 ({ns['size_kb']} KB)")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
