import asyncio
import os
import platform
import re
import time
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

from fastmcp import Context

DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "").strip()
DOWNLOAD_SOUND = os.getenv("DOWNLOAD_SOUND", "").strip()


async def download_file(
    url: str,
    save_dir: str = "",
    filename: str = "",
    ctx: Optional[Context] = None,  # type: ignore
) -> str:
    """下载网络文件到本地。
    - url: 文件链接
    - save_dir: 保存目录（可选，默认 DOWNLOAD_DIR 环境变量或 ./downloads/）
    - filename: 文件名（可选，默认从 URL 或响应头提取）
    支持下载进度上报和完成提示音。"""

    if not url.startswith(("http://", "https://")):
        return f"错误：无效的 URL - {url}"

    try:
        target_dir = _resolve_dir(save_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            head = await client.head(url)
            head.raise_for_status()
            total_size = int(head.headers.get("content-length", 0))

        if not filename:
            filename = _extract_filename(url, head)

        filename = _sanitize_filename(filename)
        filepath = _resolve_path(target_dir, filename)

        downloaded = 0
        last_report = 0
        start_time = time.time()

        async with httpx.AsyncClient(timeout=3600, follow_redirects=True) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()

                with open(filepath, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=8192):
                        f.write(chunk)
                        downloaded += len(chunk)

                        if ctx and downloaded - last_report >= 524288:
                            await ctx.report_progress(
                                downloaded,
                                total_size,
                                _progress_msg(downloaded, total_size),
                            )
                            last_report = downloaded

        elapsed = time.time() - start_time
        speed = downloaded / elapsed / 1024 if elapsed > 0 else 0
        actual_size = filepath.stat().st_size

        if total_size and actual_size != total_size:
            return f"警告：文件大小不匹配（期望 {_fmt_size(total_size)}，实际 {_fmt_size(actual_size)}）\n文件已保存: {filepath}"

        _play_sound()
        return (
            f"下载完成！\n"
            f"文件: {filepath}\n"
            f"大小: {_fmt_size(actual_size)}\n"
            f"耗时: {elapsed:.1f}s | 速度: {speed:.1f} KB/s"
        )

    except httpx.HTTPStatusError as e:
        return f"下载失败：HTTP {e.response.status_code}"
    except Exception as e:
        return f"下载出错: {e}"


def _resolve_dir(save_dir: str) -> Path:
    if save_dir:
        return Path(save_dir)
    if DOWNLOAD_DIR:
        return Path(DOWNLOAD_DIR)
    return Path(__file__).resolve().parent / "downloads"


def _extract_filename(url: str, head_response) -> str:
    cd = head_response.headers.get("content-disposition", "")
    if cd:
        match = re.search(r'filename[^;=\n]*=["\']?([^"\';\n]*)', cd, re.I)
        if match:
            return match.group(1).strip()
    return Path(url.split("?")[0]).name or "downloaded_file"


def _sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = name.strip(". ")
    return name or "downloaded_file"


def _resolve_path(target_dir: Path, filename: str) -> Path:
    candidate = target_dir / filename
    if not candidate.exists():
        return candidate
    stem, ext = os.path.splitext(filename)
    i = 1
    while True:
        candidate = target_dir / f"{stem}_{i}{ext}"
        if not candidate.exists():
            return candidate
        i += 1


def _progress_msg(downloaded: int, total: int) -> str:
    if total:
        pct = downloaded / total * 100
        return (
            f"{_fmt_size(downloaded)} / {_fmt_size(total)}  ({pct:.1f}%)"
        )
    return f"{_fmt_size(downloaded)} (大小未知)"


def _fmt_size(size: int) -> str:
    if size >= 1073741824:
        return f"{size / 1073741824:.1f} GB"
    if size >= 1048576:
        return f"{size / 1048576:.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def _play_sound():
    try:
        if DOWNLOAD_SOUND and Path(DOWNLOAD_SOUND).exists():
            import winsound

            winsound.PlaySound(DOWNLOAD_SOUND, winsound.SND_FILENAME)
            return
    except Exception:
        pass

    try:
        if platform.system() == "Windows":
            import winsound

            winsound.MessageBeep(-1)
    except Exception:
        pass
