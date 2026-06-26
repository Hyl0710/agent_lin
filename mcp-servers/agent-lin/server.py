import os
import re
from pathlib import Path

from fastmcp import FastMCP
from dotenv import load_dotenv

from ddgs import DDGS

load_dotenv()
mcp = FastMCP("agent-lin")

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
_has_tavily = bool(TAVILY_API_KEY and TAVILY_API_KEY.startswith("tvly-") and "替换" not in TAVILY_API_KEY)

@mcp.tool()
def web_search(query: str, max_results: int = 5) -> str:
    """搜索网络信息，返回结果列表（含标题、摘要、来源链接）。
    适合用来回答用户的问题，并给出资料来源。"""
    lines = []
    try:
        with DDGS() as ddgs:
            for i, r in enumerate(ddgs.text(query, max_results=max_results), 1):
                lines.append(f"{i}. {r['title']}")
                lines.append(f"   摘要: {r['body']}")
                lines.append(f"   来源: {r['href']}")
                lines.append("")
    except Exception as e:
        lines.append(f"[DuckDuckGo 搜索出错: {e}]")

    if _has_tavily:
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=TAVILY_API_KEY)
            tavily_result = client.search(query, max_results=max_results)
            if tavily_result.get("results"):
                lines.append("--- Tavily 搜索结果 ---")
                for i, r in enumerate(tavily_result["results"], 1):
                    lines.append(f"{i}. {r.get('title', '无标题')}")
                    lines.append(f"   摘要: {r.get('content', '无内容')}")
                    lines.append(f"   来源: {r.get('url', '无链接')}")
                    lines.append("")
        except Exception as e:
            lines.append(f"[Tavily 搜索出错: {e}]")

    return "\n".join(lines) if lines else "未找到相关结果。"

@mcp.tool()
def reverse_image_search(image_path: str) -> str:
    """以图搜图：传入本地图片路径，检索该图片的来源和相关网页。
    适合用来查找图片的原始出处、类似图片等。"""
    img_path = Path(image_path)
    if not img_path.exists():
        return f"错误：文件不存在 - {image_path}"

    try:
        results = []
        with DDGS() as ddgs:
            # 用图片文件名和目录名辅助搜索
            query = img_path.stem
            for r in ddgs.text(query, max_results=5):
                results.append(f"{r['title']}")
                results.append(f"   摘要: {r['body']}")
                results.append(f"   链接: {r['href']}")
                results.append("")

        output = [f"图片: {image_path}"]
        output.append(f"大小: {img_path.stat().st_size / 1024:.1f} KB")
        output.append("")
        output.append("=== 相关搜索结果 ===")
        output.extend(results)
        return "\n".join(output) if results else "未找到相关的图片来源信息。"

    except Exception as e:
        return f"以图搜图出错: {e}"

@mcp.tool()
def fetch_webpage(url: str) -> str:
    """爬取指定网页的内容，以纯文本形式返回。
    适合用来下载网页内容、文章正文等。"""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        import httpx
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        resp.raise_for_status()

        from html.parser import HTMLParser

        class TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text_parts = []
                self.skip_tag = False
            def handle_starttag(self, tag, attrs):
                if tag in ("script", "style", "nav", "footer", "header"):
                    self.skip_tag = True
                if tag in ("p", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"):
                    self.text_parts.append("\n")
            def handle_endtag(self, tag):
                if tag in ("script", "style", "nav", "footer", "header"):
                    self.skip_tag = False
            def handle_data(self, data):
                if not self.skip_tag:
                    text = data.strip()
                    if text:
                        self.text_parts.append(text + " ")

        extractor = TextExtractor()
        extractor.feed(resp.text)
        content = "".join(extractor.text_parts)

        content = re.sub(r"\n{3,}", "\n\n", content)

        lines = [
            f"URL: {url}",
            f"状态码: {resp.status_code}",
            f"内容类型: {resp.headers.get('content-type', '未知')}",
            "",
            "=== 页面内容 ===",
            content[:8000]  # 限制 8000 字符
        ]

        if len(content) > 8000:
            lines.append("\n... (内容较长，已截断前 8000 字符)")

        return "\n".join(lines)

    except Exception as e:
        return f"网页爬取出错: {e}"

if __name__ == "__main__":
    mcp.run()
