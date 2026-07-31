import json
import re
import ssl
import time
import yt_dlp
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from .config import TEMP_DIR, FFMPEG_PATH
from .logger import logger
from .utils import time_it


class VideoDownloader:
    def __init__(self, audio_only=True, cookie_header: str | None = None):
        self.audio_only = audio_only
        self.cookie_header = cookie_header
        self.ydl_opts = {
            "format": "bestaudio/best" if audio_only else "bestvideo+bestaudio/best",
            "outtmpl": str(TEMP_DIR / "%(title)s.%(ext)s"),
            "ffmpeg_location": str(FFMPEG_PATH.parent),
            "quiet": True,
            "no_warnings": True,
        }
        if cookie_header:
            self.ydl_opts["http_headers"] = {"Cookie": cookie_header}

        if not audio_only:
            self.ydl_opts["merge_output_format"] = "mp4"

    def _extract_bvid(self, url: str) -> str | None:
        patterns = [
            r"bv[Ii]([A-Za-z0-9]{10})",
            r"BV([A-Za-z0-9]{10})",
            r"([A-Za-z0-9]{10})",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                bvid = match.group(1) if match.group(1) else match.group(0)
                if len(bvid) == 10:
                    return f"BV{bvid}"
        return None

    def _get_bilibili_metadata(self, url: str) -> dict | None:
        bvid = self._extract_bvid(url)
        if not bvid:
            return None

        api_url = (
            f"https://api.bilibili.com/x/web-interface/view?{urlencode({'bvid': bvid})}"
        )
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.bilibili.com/",
        }
        if self.cookie_header:
            headers["Cookie"] = self.cookie_header

        try:
            req = Request(api_url, headers=headers)
            try:
                response = urlopen(req, timeout=10)
            except Exception:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                response = urlopen(req, timeout=10, context=ctx)
            with response:
                data = json.loads(response.read().decode())
                if data.get("code") == 0:
                    return data.get("data")
        except Exception as e:
            logger.warning(f"API metadata fetch failed: {e}")
        return None

    def _get_playurl(self, avid: int, cid: int, qn: int = 80) -> dict | None:
        api_url = f"https://api.bilibili.com/x/player/playurl?{urlencode({'avid': avid, 'cid': cid, 'qn': qn, 'fnval': 4048})}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.bilibili.com/",
        }
        if self.cookie_header:
            headers["Cookie"] = self.cookie_header

        try:
            req = Request(api_url, headers=headers)
            try:
                response = urlopen(req, timeout=15)
            except Exception:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                response = urlopen(req, timeout=15, context=ctx)
            with response:
                data = json.loads(response.read().decode())
                if data.get("code") == 0:
                    return data.get("data", {})
        except Exception as e:
            logger.warning(f"PlayURL API failed: {e}")
        return None

    def _download_url(self, url: str, output_path: Path, max_retries: int = 3):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.bilibili.com/",
        }
        if self.cookie_header:
            headers["Cookie"] = self.cookie_header

        last_error = None
        for attempt in range(max_retries):
            try:
                req = Request(url, headers=headers)
                # Try with SSL verification first, fallback to unverified
                try:
                    response = urlopen(req, timeout=600)
                except Exception:
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    response = urlopen(req, timeout=600, context=ctx)

                with response, open(output_path, "wb") as f:
                    total = int(response.headers.get("Content-Length", 0))
                    downloaded = 0
                    chunk_size = 8192
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = downloaded * 100 // total
                            if downloaded % (chunk_size * 50) == 0:
                                logger.info(f"  📥 {pct}%")
                return  # success
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait = 5 * (attempt + 1)
                    logger.warning(f"  ⚠️ Download attempt {attempt+1} failed: {e}, retrying in {wait}s...")
                    time.sleep(wait)
                    # Re-download from scratch (could add range header for resume)
                else:
                    raise last_error

    def extract_info(self, url: str):
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception as e:
            logger.warning(f"yt-dlp extract failed: {e}, trying Bilibili API...")
            metadata = self._get_bilibili_metadata(url)
            if metadata:
                return {
                    "id": metadata.get("aid"),
                    "title": metadata.get("title"),
                    "uploader": metadata.get("owner", {}).get("name"),
                    "upload_date": metadata.get("pubdate"),
                    "duration": metadata.get("duration"),
                    "description": metadata.get("desc"),
                }
            raise

    @time_it
    def download(self, url: str, info: dict | None = None):
        """
        下载并返回 (本地文件路径, UP主姓名, 发布日期)。
        """
        logger.info(f"🚀 Analyzing URL: {url}...")

        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = info or ydl.extract_info(url, download=False)
                uploader = info.get("uploader", "Unknown")
                upload_date = info.get("upload_date", "Unknown")

                if upload_date != "Unknown" and len(upload_date) == 8:
                    upload_date = (
                        f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
                    )

                temp_filename = ydl.prepare_filename(info)
                temp_path = Path(temp_filename)

                logger.info(
                    f"⬇️  Downloading {'audio' if self.audio_only else 'video'}..."
                )
                ydl.download([url])

                if info.get("requested_downloads"):
                    filename = info["requested_downloads"][0]["filepath"]
                else:
                    filename = ydl.prepare_filename(info)

                filepath = Path(filename)

                if not filepath.exists():
                    candidates = list(TEMP_DIR.glob(f"{temp_path.stem}.*"))
                    if candidates:
                        filepath = candidates[0]

                logger.info(f"✅ Download complete: {filepath.name}")
                return filepath, uploader, upload_date
        except Exception as e:
            logger.warning(f"yt-dlp download failed: {e}, trying Bilibili API...")
            return self._download_via_api(url, info)

    def _download_via_api(self, url: str, info: dict | None = None):
        """Fallback: 使用 Bilibili API 下载音频"""
        bvid = self._extract_bvid(url)
        if not bvid:
            raise Exception("无法提取 BVID")

        metadata = self._get_bilibili_metadata(url)
        if not metadata:
            raise Exception("无法获取视频信息")

        avid = metadata.get("aid")
        cid = metadata.get("cid")
        title = metadata.get("title", "unknown")

        uploader = metadata.get("owner", {}).get("name", "Unknown")
        pubdate = metadata.get("pubdate")
        upload_date = "Unknown"
        if pubdate:
            from datetime import datetime

            upload_date = datetime.fromtimestamp(pubdate).strftime("%Y-%m-%d")

        playurl_data = self._get_playurl(avid, cid)
        if not playurl_data:
            raise Exception("无法获取播放地址")

        dash = playurl_data.get("dash", {})
        audio_url = None

        if dash and dash.get("audio"):
            audio_url = dash["audio"][0].get("baseUrl") or dash["audio"][0].get("url")

        if not audio_url:
            raise Exception("无法获取音频流地址")

        safe_title = "".join(c for c in title if c.isalnum() or c in " _-").strip()[:50]
        output_path = TEMP_DIR / f"{safe_title}.m4s"

        logger.info(f"⬇️  Downloading audio via API...")
        self._download_url(audio_url, output_path)

        logger.info(f"✅ Download complete: {output_path.name}")
        return output_path, uploader, upload_date
