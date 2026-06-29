import asyncio
import hashlib
import re
from html.parser import HTMLParser
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

from cache_manager import get_cache

CACHE_TTL_WEBPAGE = 86400


async def fetch_webpage(url: str) -> str:
    """爬取指定网页的内容，以纯文本形式返回。
    适合用来下载网页内容、文章正文等。"""

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    cache = get_cache()
    cached = await cache.get("webpage", url)
    if cached is not None:
        return cached

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.bilibili.com/",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()

        content = _extract_text(resp.text)
        lines = [
            f"URL: {url}",
            f"状态码: {resp.status_code}",
            f"内容类型: {resp.headers.get('content-type', '未知')}",
            "",
            "=== 页面内容 ===",
            content[:8000],
        ]

        if len(content) > 8000:
            lines.append("\n... (内容较长，已截断前 8000 字符)")

        result = "\n".join(lines)
        await cache.set("webpage", url, result, ttl=CACHE_TTL_WEBPAGE)
        return result

    except Exception as e:
        return f"网页爬取出错: {e}"


def _extract_text(html: str) -> str:
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
    extractor.feed(html)
    content = "".join(extractor.text_parts)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content
