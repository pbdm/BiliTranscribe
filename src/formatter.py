from pathlib import Path
import datetime
from .logger import logger
from .utils import time_it

class MarkdownFormatter:
    def _format_timestamp(self, seconds: float) -> str:
        """将秒数转换为 HH:MM:SS 格式"""
        total_seconds = int(seconds)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    @time_it
    def save(self, segments, output_path: Path, title: str, source_url: str, uploader: str = "Unknown", upload_date: str = "Unknown"):
        logger.info(f"✍️  Saving markdown to {output_path}...")
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        clean_url = source_url.split("?")[0] if "?" in source_url else source_url
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("---\n")
            f.write(f"pubDate: {current_time}\n")
            f.write(f"published: {upload_date}\n")
            f.write(f"source: {source_url}\n")
            f.write(f"author: {uploader}\n")
            f.write("publish: false\n")
            f.write("tags:\n  - transcript\n  - inbox\n")
            f.write("---\n\n")
            
            # 2. 写入标题
            f.write(f"# {title}\n\n")
            
            # 3. 写入内容
            for item in segments:
                item_type = getattr(item, "type", "speech")
                start_str = self._format_timestamp(item.start)
                start_seconds = int(item.start)
                text = item.text.strip()
                timestamp_link = f"{clean_url}?t={start_seconds}"
                if item_type == "ocr":
                    f.write(f"> [!abstract] 📺 画面文字 ({start_str})\n")
                    for line in text.split("\n"):
                        f.write(f"> {line}\n")
                    f.write("\n")
                else:
                    f.write(f"- [{start_str}]({timestamp_link}) {text}\n")
        logger.info("✅ Markdown saved successfully.")
