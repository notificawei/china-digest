#!/usr/bin/env python3
"""
朝鲜局势情报内参 · 自动生成脚本
每日抓取 RSS，渲染为报纸风格 HTML，输出到 docs/dprk/index.html
"""

import feedparser
import requests
import html as htmllib
import sys
import re
from datetime import datetime, timezone
from pathlib import Path

try:
    from deep_translator import GoogleTranslator
    HAS_TRANSLATOR = True
except ImportError:
    HAS_TRANSLATOR = False

# ============================================================
# RSS 来源配置
# ============================================================

COLUMN_1 = {
    "label": "🔬 智库分析",
    "en_label": "Think Tank & Analysis",
    "sources": [
        {
            "name": "NK Pro",
            "url": "https://www.nknews.org/feed/",
        },
        {
            "name": "38 North",
            "url": "https://www.38north.org/feed/",
        },
        {
            "name": "Beyond Parallel (CSIS)",
            "url": "https://beyondparallel.csis.org/feed/",
        },
        {
            "name": "Daily NK",
            "url": "https://www.dailynk.com/english/feed/",
        },
    ],
}

COLUMN_2 = {
    "label": "🇰🇷 韩国媒体",
    "en_label": "South Korean Media",
    "sources": [
        {
            "name": "Yonhap News",
            "url": "https://en.yna.co.kr/RSS/news.xml",
        },
        {
            "name": "Korea Times",
            "url": "https://www.koreatimes.co.kr/www/rss/rss.xml",
        },
        {
            "name": "Korea Herald",
            "url": "https://www.koreaherald.com/rss/020100000000.xml",
        },
    ],
}

COLUMN_3 = {
    "label": "📢 朝鲜官方",
    "en_label": "DPRK Official Media",
    "sources": [
        # KCNA Watch 域名不稳定，暂用朝中社英文版替代
        {
            "name": "KCNA (English)",
            "url": "https://kcna.kp/en/rss",
        },
    ],
}

# ============================================================
# 工具函数
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

_translator_cache = {}

def translate(text, max_chars=300):
    """翻译英文为中文，失败时返回空字符串"""
    if not HAS_TRANSLATOR or not text:
        return ""
    text = text[:max_chars]
    if text in _translator_cache:
        return _translator_cache[text]
    try:
        result = GoogleTranslator(source="auto", target="zh-CN").translate(text)
        _translator_cache[text] = result or ""
        return _translator_cache[text]
    except Exception:
        return ""


def clean_text(raw, max_chars=250):
    if not raw:
        return ""
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = htmllib.unescape(raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    if len(raw) > max_chars:
        raw = raw[:max_chars].rsplit(" ", 1)[0] + "…"
    return raw


def get_date(entry):
    for field in ("published_parsed", "updated_parsed"):
        t = getattr(entry, field, None)
        if t:
            try:
                dt = datetime(*t[:6], tzinfo=timezone.utc)
                return dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
    for field in ("published", "updated"):
        raw = getattr(entry, field, None)
        if raw:
            try:
                from email.utils import parsedate_to_datetime
                return parsedate_to_datetime(raw).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
    return ""


def sort_key(entry):
    d = get_date(entry)
    return d if d else "0000-00-00 00:00"

# ============================================================
# 抓取
# ============================================================

def fetch_source(source_cfg):
    url = source_cfg["url"]
    name = source_cfg["name"]
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        if not feed.entries:
            print(f"  ⚠️  {name}: 无内容", file=sys.stderr)
            return []
    except Exception as e:
        print(f"  ❌ {name}: {e}", file=sys.stderr)
        return []

    results = []
    for entry in feed.entries[:40]:
        entry._source_name = name
        results.append(entry)

    print(f"  ✓  {name}: {len(results)} 条", file=sys.stderr)
    return results


def fetch_column(col_cfg):
    data = {}
    for src in col_cfg["sources"]:
        data[src["name"]] = fetch_source(src)
    return data

# ============================================================
# HTML 渲染
# ============================================================

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: "Georgia", "Times New Roman", "宋体", serif;
  background: #f9f7f2; color: #1a1a1a; line-height: 1.7;
}
.page-wrap { max-width: 1280px; margin: 0 auto; padding: 2.5rem 1.5rem 4rem; }
.columns {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 2rem; align-items: start;
}
.columns > div { min-width: 0; overflow-wrap: break-word; word-break: break-word; }
@media (max-width: 860px) { .columns { grid-template-columns: 1fr; } }
.masthead {
  text-align: center;
  border-top: 3px solid #1a1a1a; border-bottom: 3px solid #1a1a1a;
  padding: 1.2rem 0; margin-bottom: 2.5rem;
}
.masthead h1 { font-size: 2rem; font-weight: 700; letter-spacing: 0.08em; }
.masthead .nav {
  margin-top: 0.7rem;
  font-family: "Helvetica Neue", Arial, sans-serif; font-size: 0.8rem;
}
.masthead .nav a {
  color: #888; text-decoration: none; margin: 0 0.6rem;
  letter-spacing: 0.05em; text-transform: uppercase;
}
.masthead .nav a:hover { color: #1a1a1a; text-decoration: underline; }
.masthead .nav .active { color: #1a1a1a; font-weight: 600; margin: 0 0.6rem; letter-spacing: 0.05em; text-transform: uppercase; }
.masthead .meta {
  font-size: 0.82rem; color: #666; margin-top: 0.4rem;
  font-family: "Helvetica Neue", Arial, sans-serif; letter-spacing: 0.05em;
}
.section { margin-bottom: 2.8rem; }
.section-header {
  display: flex; align-items: baseline; gap: 0.8rem;
  border-bottom: 1.5px solid #1a1a1a; padding-bottom: 0.4rem; margin-bottom: 1.4rem;
}
.section-header h2 { font-size: 1.15rem; font-weight: 700; letter-spacing: 0.04em; }
.section-header .en-label {
  font-size: 0.75rem; color: #888;
  font-family: "Helvetica Neue", Arial, sans-serif;
  text-transform: uppercase; letter-spacing: 0.08em;
}
.entry { border-bottom: 0.5px solid #ddd; padding: 0.9rem 0; }
.entry:last-child { border-bottom: none; }
.entry-title-en {
  font-size: 1rem; font-weight: 700; color: #1a1a1a;
  margin-bottom: 0.15rem; font-family: "Georgia", serif;
}
.entry-title-en a { color: inherit; text-decoration: none; }
.entry-title-en a:hover { text-decoration: underline; }
.entry-title-zh { font-size: 0.82rem; color: #777; margin-bottom: 0.4rem; font-style: italic; }
.entry-summary {
  font-size: 0.88rem; color: #444; line-height: 1.65;
  font-family: "Helvetica Neue", Arial, sans-serif;
}
.entry-meta { font-size: 0.75rem; color: #999; margin-top: 0.4rem; font-family: "Helvetica Neue", Arial, sans-serif; }
.source-label {
  font-size: 0.72rem; font-family: "Helvetica Neue", Arial, sans-serif;
  text-transform: uppercase; letter-spacing: 0.1em; color: #888;
  border-left: 2px solid #ccc; padding-left: 0.5rem; margin: 1.4rem 0 0.8rem;
}
.no-articles { font-size: 0.88rem; color: #999; font-style: italic; padding: 0.5rem 0; font-family: "Helvetica Neue", Arial, sans-serif; }
.footer {
  text-align: center; font-size: 0.75rem; color: #bbb;
  border-top: 1px solid #ddd; padding-top: 1.5rem; margin-top: 3rem;
  font-family: "Helvetica Neue", Arial, sans-serif; letter-spacing: 0.03em;
}
"""


def esc(s):
    return htmllib.escape(str(s or ""), quote=True)


def render_entry(entry):
    title_en = esc(clean_text(entry.get("title", ""), max_chars=200))
    link = esc(entry.get("link", "#") or "#")
    summary = esc(clean_text(entry.get("summary", "") or entry.get("description", ""), max_chars=250))
    date = esc(get_date(entry))

    title_zh = esc(translate(entry.get("title", "")))
    title_zh_html = f'<div class="entry-title-zh">{title_zh}</div>' if title_zh else ""

    return f"""
    <div class="entry">
      <div class="entry-title-en"><a href="{link}" target="_blank">{title_en}</a></div>
      {title_zh_html}
      <div class="entry-summary">{summary}</div>
      <div class="entry-meta">{date}</div>
    </div>"""


def render_column(col_cfg, data_dict):
    label = esc(col_cfg["label"])
    en_label = esc(col_cfg["en_label"])

    parts = [f"""
  <div class="section">
    <div class="section-header">
      <h2>{label}</h2>
      <span class="en-label">{en_label}</span>
    </div>"""]

    for src in col_cfg["sources"]:
        name = src["name"]
        entries = data_dict.get(name, [])
        parts.append(f'    <div class="source-label">{esc(name)}</div>')
        if entries:
            sorted_entries = sorted(entries, key=sort_key, reverse=True)
            for e in sorted_entries[:6]:
                parts.append(render_entry(e))
        else:
            parts.append('    <p class="no-articles">暂无文章（抓取失败或无相关内容）</p>')

    parts.append("  </div>")
    return "\n".join(parts)


def render_html(col1_data, col2_data, col3_data, date_str):
    col1_html = render_column(COLUMN_1, col1_data)
    col2_html = render_column(COLUMN_2, col2_data)
    col3_html = render_column(COLUMN_3, col3_data)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>朝鲜局势情报内参 · {date_str}</title>
<style>
{CSS}
</style>
</head>
<body>
<div class="page-wrap">
  <div class="masthead">
    <h1>朝鲜局势情报内参</h1>
    <div class="nav">
      <a href="/china-digest/">中国</a>
      <span class="active">朝鲜</span>
    </div>
    <div class="meta">DPRK INTELLIGENCE DIGEST &nbsp;·&nbsp; {date_str} &nbsp;·&nbsp; 自动生成</div>
  </div>
  <div class="columns">
{col1_html}
{col2_html}
{col3_html}
  </div>
  <div class="footer">
    本文件由脚本自动生成 · 内容来自各媒体 RSS · 仅供参考
  </div>
</div>
</body>
</html>"""

# ============================================================
# 主入口
# ============================================================

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    docs_dir = Path(__file__).parent / "docs" / "dprk"
    docs_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n生成 DPRK {today} 日报...\n", file=sys.stderr)

    print("【第一栏 · 智库分析】", file=sys.stderr)
    col1_data = fetch_column(COLUMN_1)

    print("\n【第二栏 · 韩国媒体】", file=sys.stderr)
    col2_data = fetch_column(COLUMN_2)

    print("\n【第三栏 · 朝鲜官方】", file=sys.stderr)
    col3_data = fetch_column(COLUMN_3)

    html_content = render_html(col1_data, col2_data, col3_data, today)

    out = docs_dir / "index.html"
    out.write_text(html_content, encoding="utf-8")
    print(f"\n✅ 已生成：{out}", file=sys.stderr)


if __name__ == "__main__":
    main()
