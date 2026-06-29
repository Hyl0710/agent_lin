import asyncio
import hashlib
from pathlib import Path

import httpx
from ddgs import DDGS
from dotenv import load_dotenv

load_dotenv()

import os

from cache_manager import get_cache

SAUCENAO_API_KEY = os.getenv("SAUCENAO_API_KEY", "").strip()


async def reverse_image_search(image_path: str) -> str:
    """以图搜图：传入本地图片路径，通过 SauceNAO 检索视觉相似的图片来源。
    搜索失败时自动降级为文件名搜索。
    适合用来查找图片的原始出处、类似图片等。"""

    img_path = Path(image_path)
    if not img_path.exists():
        return f"错误：文件不存在 - {image_path}"

    md5 = _file_md5(image_path)
    cache = get_cache()
    cached = await cache.get("image", md5)
    if cached is not None:
        return cached

    saucenao_result = await _search_saucenao(image_path, img_path)

    if saucenao_result:
        await cache.set("image", md5, saucenao_result, ttl=86400 * 90)
        return saucenao_result

    fallback = await _fallback_ddgs(image_path, img_path)
    await cache.set("image", md5, fallback, ttl=86400 * 7)
    return fallback


async def _search_saucenao(image_path: str, img_path: Path) -> str | None:
    try:
        file_size = img_path.stat().st_size

        async with httpx.AsyncClient(timeout=45) as client:
            params = {"output_type": 2, "numres": 5}
            if SAUCENAO_API_KEY:
                params["api_key"] = SAUCENAO_API_KEY

            files = {"file": (img_path.name, img_path.read_bytes())}
            resp = await client.post(
                "https://saucenao.com/search.php", params=params, files=files
            )
            resp.raise_for_status()
            data = resp.json()

        header = data.get("header", {})
        status = header.get("status", -1)

        if status < 0:
            return None

        results = data.get("results", [])
        if not results:
            return None

        lines = [
            f"图片: {image_path}",
            f"MD5: {_file_md5(image_path)}",
            f"大小: {file_size / 1024:.1f} KB",
            "",
            "=== SauceNAO 以图搜图结果 ===",
            "",
        ]

        for i, r in enumerate(results, 1):
            h = r.get("header", {})
            d = r.get("data", {})
            similarity = float(h.get("similarity", "0"))
            ext_urls = d.get("ext_urls", [])
            url = ext_urls[0] if ext_urls else "无链接"

            lines.append(f"{i}. 相似度: {similarity:.1f}% | 来源: {h.get('index_name', '未知')}")
            if d.get("title"):
                lines.append(f"   标题: {d['title']}")
            if d.get("member_name"):
                lines.append(f"   作者: {d['member_name']}")
            lines.append(f"   链接: {url}")
            lines.append("")

        remaining = header.get("long_remaining", "?")
        short_remaining = header.get("short_remaining", "?")
        lines.append(
            f"--- 今日剩余: {remaining} 次 | 短时剩余: {short_remaining} 次 ---"
        )

        return "\n".join(lines)

    except Exception:
        return None


async def _fallback_ddgs(image_path: str, img_path: Path) -> str:
    lines = [
        f"图片: {image_path}",
        f"MD5: {_file_md5(image_path)}",
        f"大小: {img_path.stat().st_size / 1024:.1f} KB",
        "",
        "=== (SauceNAO 不可用，降级为文件名搜索) ===",
        "",
    ]

    try:
        query = _build_fallback_query(img_path)

        results = await asyncio.to_thread(_ddgs_text_search, query)
        for r in results:
            lines.append(f"{r['title']}")
            lines.append(f"   摘要: {r['body']}")
            lines.append(f"   链接: {r['href']}")
            lines.append("")

        if not results:
            lines.append("未找到相关结果。")
    except Exception as e:
        lines.append(f"搜索出错: {e}")

    return "\n".join(lines)


def _ddgs_text_search(query: str, max_results: int = 5) -> list[dict]:
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append(r)
    return results


def _build_fallback_query(img_path: Path) -> str:
    parent = img_path.parent.name.strip()
    stem = img_path.stem.strip()
    if parent and parent not in (".", ".."):
        return f"{stem} {parent}"
    return stem


def _file_md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
