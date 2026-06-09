import argparse
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.absolute()
sys.path.append(str(PROJECT_ROOT))

from src.downloader import VideoDownloader
from src.audio import AudioExtractor
from src.utils import sanitize_filename
from src.subtitles import SubtitleFetcher
from src.transcriber import Transcriber
from src.formatter import MarkdownFormatter
from src.config import (
    TRANSCRIPT_DIR,
    TEMP_DIR,
    OUTPUT_DIR,
    DEFAULT_COMPUTE_TYPE,
    DEFAULT_DEVICE,
    DEFAULT_NUM_WORKERS,
    DEFAULT_MODEL_SIZE,
)
from src.logger import logger, safe_print
from src.utils import time_it


class ContentItem:
    def __init__(self, start, text, type="speech"):
        self.start = start
        self.text = text
        self.type = type


@time_it
def select_model_by_duration(
    duration_seconds: float, user_model: str, user_fast: bool, default_model: str
):
    duration_minutes = duration_seconds / 60
    if user_fast:
        return "base", True
    if user_model != default_model:
        return user_model, user_fast
    if duration_minutes < 10:
        return default_model, False
    elif duration_minutes < 30:
        return "base", False
    else:
        return "base", True


def process_pipeline(args):
    formatter = MarkdownFormatter()
    media_path = None
    audio_path = None

    subtitle_fetcher = SubtitleFetcher()
    downloader = VideoDownloader()
    extractor = AudioExtractor()

    info = subtitle_fetcher.extract_info(args.url)
    video_title, uploader, upload_date = subtitle_fetcher.get_video_metadata(info)

    duration = info.get("duration", 0)
    duration_minutes = duration / 60 if duration else 0
    logger.info(f"📹 Video duration: {duration_minutes:.1f} minutes")

    auto_model, auto_fast = select_model_by_duration(
        duration, args.model, args.fast, DEFAULT_MODEL_SIZE
    )
    if args.model != auto_model or args.fast != auto_fast:
        logger.info(f"⚡ Auto-selected model: {auto_model}, fast: {auto_fast}")
        args.model = auto_model
        args.fast = auto_fast

    # 优先尝试使用 B站字幕
    content_items, subtitle_source, subtitle_language = subtitle_fetcher.fetch(
        info, prefer_subtitle=True
    )

    if not content_items:
        logger.info("ℹ️ No usable subtitle track found, falling back to ASR.")

        # 1. 下载音频
        media_path, uploader, upload_date = downloader.download(args.url, info=info)
        video_title = media_path.stem

        # 2. 提取音频
        audio_path = extractor.extract(media_path)

        # 3. 转录
        if args.engine == "funasr":
            try:
                from src.transcriber_funasr import FunASRTranscriber

                transcriber = FunASRTranscriber()
            except Exception as e:
                logger.error(f"❌ FunASR load error: {e}")
                sys.exit(1)
        else:
            compute_type = args.compute_type
            num_workers = 4 if args.fast else DEFAULT_NUM_WORKERS
            logger.info(
                f"Engine: Whisper ({args.model}) | Device: {args.device} | Compute: {compute_type} | Workers: {num_workers}"
            )
            transcriber = Transcriber(
                model_size=args.model,
                device=args.device,
                compute_type=compute_type,
                num_workers=num_workers,
            )

        logger.info("⚡ Starting ASR inference...")
        content_items = []
        for seg in transcriber.transcribe(audio_path):
            content_items.append(ContentItem(seg.start, seg.text, "speech"))

        transcript_source = "whisper"
    else:
        transcript_source = "subtitle"
        logger.info(f"✅ Using {subtitle_source} subtitle")

    # 4. 保存原始文稿到临时目录
    md_filename = f"{uploader}-{sanitize_filename(video_title)}_{transcript_source}.md"
    local_md_path = TEMP_DIR / md_filename

    logger.info(f"📂 Saving raw transcript to: {local_md_path}")
    formatter.save(
        content_items,
        local_md_path,
        title=video_title,
        source_url=args.url,
        uploader=uploader,
        upload_date=upload_date,
    )
    safe_print(f"TRANSCRIPT_SAVED: {local_md_path.absolute()}")

    safe_print("\n" + "=" * 60)
    safe_print("🚀 [ACTION REQUIRED] Agent Skill Triggered")
    safe_print("Please read the transcript above and generate a summary note.")
    safe_print(
        "CRITICAL: You MUST first read and strictly follow the formatting rules in `PROMPT.md` (located in the project root) before generating your response."
    )
    safe_print(f"OUTPUT_DIR: {OUTPUT_DIR.absolute()}")
    safe_print("=" * 60 + "\n")

    # 5. 清理临时文件
    if media_path and media_path.exists():
        os.remove(media_path)
    if not args.keep_audio and audio_path and audio_path.exists():
        os.remove(audio_path)
        logger.info("🗑️  Temporary audio file removed.")


def main():
    parser = argparse.ArgumentParser(
        description="BiliTranscribe: Download and transcribe Bilibili videos to Markdown."
    )
    parser.add_argument("url", help="Bilibili video URL")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL_SIZE,
        help=f"Whisper model size (default: {DEFAULT_MODEL_SIZE})",
    )
    parser.add_argument(
        "--keep-audio", action="store_true", help="Keep the intermediate WAV audio file"
    )
    parser.add_argument(
        "--engine",
        choices=["whisper", "funasr"],
        default="whisper",
        help="ASR engine (default: whisper)",
    )
    parser.add_argument("--fast", action="store_true", help="Speed mode")
    parser.add_argument(
        "--device", default=DEFAULT_DEVICE, help=f"Device (default: {DEFAULT_DEVICE})"
    )
    parser.add_argument(
        "--compute-type",
        default=DEFAULT_COMPUTE_TYPE,
        help=f"Compute type (default: {DEFAULT_COMPUTE_TYPE})",
    )

    args = parser.parse_args()

    try:
        process_pipeline(args)
        logger.info("✨ All processes completed successfully!")
    except Exception as e:
        logger.error(f"💥 Critical Error: {e}")
        import traceback

        logger.debug(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()

