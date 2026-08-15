#!/usr/bin/env python
"""
生成最终博客笔记的模板脚本。
使用方式：
    python src/generate_blog_note.py <transcript_path> [--output-dir OUTPUT_DIR]

自动填充：
- pubDate: 今天日期 (YYYY-MM-DD)
- published: 从转录文件 frontmatter 提取的 upload_date
"""
import argparse
import re
from pathlib import Path
from datetime import datetime
import yaml

def extract_frontmatter(content: str) -> dict:
    """提取 frontmatter 元数据"""
    match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if not match:
        return {}
    try:
        return yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return {}

def generate_blog_note(transcript_path: Path, output_dir: Path) -> Path:
    """从转录文件生成博客笔记模板"""
    content = transcript_path.read_text(encoding='utf-8')
    meta = extract_frontmatter(content)
    
    # 关键日期逻辑
    pub_date = datetime.now().strftime("%Y-%m-%d")          # 今天：笔记写入博客的日期
    published = meta.get('published', 'Unknown')            # 原视频/文章发布日期
    source = meta.get('source', '')
    author = meta.get('author', 'Unknown')
    title = transcript_path.stem.replace('_whisper', '').replace('CLS同学-', '').replace('黄阳的学习分享-', '')
    
    # 标签推断
    tags = ['WebNotes']
    if 'bilibili.com' in source:
        tags.append('B站视频')
    elif source.endswith('.pdf'):
        tags.append('PDF')
    else:
        tags.append('网页文章')
    
    # 输出文件名
    output_filename = f"{author}-{title}.md"
    output_path = output_dir / output_filename
    
    # 生成模板
    template = f"""---
pubDate: {pub_date}
published: {published}
source: {source}
author: {author}
publish: false
tags:
  - WebNotes
  - {tags[1] if len(tags) > 1 else '其他'}
---

> [!ABSTRACT] 核心观点
> 一句话提炼全文最重要的洞见 (TL;DR)。

## 主题一

**[核心概念] ≠ [常见误解]**

| 维度 | 对比项A | 对比项B |
|------|---------|---------|
| ... | ... | ... |

**[概念]的要点：**
1. **要点A**（简要说明）
2. **要点B**

---

### 主题二

| 分类/场景 | 方案/建议 |
|-----------|-----------|
| ... | ... |

> [!TIP] 实操建议
> 具体的行动指南或参数设置。

---

> [!WARNING] 风险提示
> (如有) 提到的风险点、局限性。
"""
    output_path.write_text(template, encoding='utf-8')
    print(f"✅ 博客笔记模板已生成: {output_path}")
    print(f"   pubDate: {pub_date} (今天)")
    print(f"   published: {published} (原内容发布日)")
    return output_path

def main():
    parser = argparse.ArgumentParser(description='从转录文件生成博客笔记模板')
    parser.add_argument('transcript', help='转录文件路径 (.md)')
    parser.add_argument('--output-dir', default='~/code/astro-blog-starter-template/src/content/blog',
                        help='输出目录 (默认: paths.json 的 OUTPUT_DIR)')
    args = parser.parse_args()
    
    transcript_path = Path(args.transcript).expanduser()
    output_dir = Path(args.output_dir).expanduser()
    
    if not transcript_path.exists():
        print(f"❌ 转录文件不存在: {transcript_path}")
        return 1
    
    output_dir.mkdir(parents=True, exist_ok=True)
    generate_blog_note(transcript_path, output_dir)
    return 0

if __name__ == '__main__':
    exit(main())