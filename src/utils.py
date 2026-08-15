import time
import functools
from datetime import datetime
from .logger import logger


def sanitize_filename(title: str, max_length: int = 100) -> str:
    """
    清理文件名，移除文件系统不友好的字符。
    - 替换 【】()（）!！?？ 等特殊符号为 -
    - 移除 | / \\ : * 等非法字符
    - 保留 alphanumeric、空格、-、_、.
    """
    result = []
    for c in title:
        if c.isalnum() or c in " -_.":
            result.append(c)
        elif c in "【】()（）!！?？":
            result.append("-")
        else:
            result.append("")
    safe = "".join(result).strip()
    # 压缩连续的 - 为单个 -
    while "--" in safe:
        safe = safe.replace("--", "-")
    # 移除首尾的 -
    safe = safe.strip("-")
    # 截断长度
    if len(safe) > max_length:
        safe = safe[:max_length]
    return safe or "untitled"


def today_str() -> str:
    """返回今天的日期字符串 (YYYY-MM-DD)，用于博客笔记的 pubDate。"""
    return datetime.now().strftime("%Y-%m-%d")


def time_it(func):
    """
    一个计时装饰器，用于测量函数的执行时间并将其记录在日志中。
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        duration = end_time - start_time
        logger.info(f"⏱️  Task '{func.__name__}' finished in {duration:.2f} seconds.")
        return result

    return wrapper
