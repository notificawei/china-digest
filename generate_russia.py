#!/usr/bin/env python3
"""
俄罗斯情报内参 · 自动生成脚本
每日抓取 RSS，渲染为报纸风格 HTML，输出到 docs/russia/index.html
"""

import feedparser
import requests
import html as htmllib
import sys
import re
from datetime import datetime, timezone
from pathlib import Path

# ============================================================
# RSS 来源配置
# ============================================================

COLUMN_1 = {
    "label": "外媒报道 · 俄朝关系",
    "en_label": "International Press · Russia–North Korea",
    "sources": [
        {
            "name": "AP",
            "url": "https://news.google.com/rss/search?q=russia+%22north+korea%22+site:apnews.com&hl=en",
        },
        {
            "name": "Reuters",
            "url": "https://news.google.com/rss/search?q=russia+%22north+korea%22+site:reuters.com&hl=en",
        },
        {
            "name": "AFP",
            "url": "https://news.google.com/rss/search?q=russia+%22north+korea%22+site:afp.com&hl=en",
        },
        {
            "name": "The Economist",
            "url": "https://news.google.com/rss/search?q=russia+%22north+korea%22+site:economist.com&hl=en",
        },
        {
            "name": "The Guardian",
            "url": "https://news.google.com/rss/search?q=russia+%22north+korea%22+site:theguardian.com&hl=en",
        },
        {
            "name": "BBC",
            "url": "https://news.google.com/rss/search?q=russia+%22north+korea%22+site:bbc.com&hl=en",
        },
    ],
}

COLUMN_2 = {
    "label": "俄媒报道 · 朝鲜",
    "en_label": "Russian Media · North Korea",
    "sources": [
        {
            "name": "TASS",
            "url": "https://tass.com/rss/v2.xml",
            "require_dprk": True,
        },
        {
            "name": "RT",
            "url": "https://www.rt.com/rss/news/",
            "require_dprk": True,
        },
        {
            "name": "Moscow Times",
            "url": "https://www.themoscowtimes.com/rss/news",
            "require_dprk": True,
        },
        {
            "name": "Meduza",
            "url": "https://meduza.io/rss/all",
            "require_dprk": True,
        },
    ],
}

COLUMN_3 = {
    "label": "俄媒报道 · 中国",
    "en_label": "Russian Media · China",
    "sources": [
        {
            "name": "TASS",
            "url": "https://tass.com/rss/v2.xml",
            "require_china": True,
        },
        {
            "name": "RT",
            "url": "https://www.rt.com/rss/news/",
            "require_china": True,
        },
        {
            "name": "Moscow Times",
            "url": "https://www.themoscowtimes.com/rss/news",
            "require_china": True,
        },
        {
            "name": "Meduza",
            "url": "https://meduza.io/rss/all",
            "require_china": True,
        },
        {
            "name": "Sputnik",
            "url": "https://news.google.com/rss/search?q=china+site:sputnikglobe.com&hl=en",
        },
    ],
}

# ============================================================
# 过滤关键词
# ============================================================

DPRK_KEYWORDS = [
    "north korea", "n. korea", "n.korea", "dprk", "kim jong", "pyongyang",
    "korean peninsula", "inter-korean", "denuclearization",
    "kim yo jong", "korean war", "unification ministry",
]

CHINA_KEYWORDS = ["china", "chinese", "beijing", "shanghai", "中国"]

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


def passes_filter(entry, source_cfg):
    title = clean_text(entry.get("title", ""), max_chars=500).lower()
    summary = clean_text(entry.get("summary", "") or entry.get("description", ""), max_chars=500).lower()
    full_text = title + " " + summary

    if source_cfg.get("require_dprk"):
        if not any(kw in full_text for kw in DPRK_KEYWORDS):
            return False

    if source_cfg.get("require_china"):
        if not any(kw in full_text for kw in CHINA_KEYWORDS):
            return False

    return True

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
    for entry in feed.entries[:100]:
        if not passes_filter(entry, source_cfg):
            continue
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
  font-family: "Georgia", "Times New Roman", serif;
  background: #ffffff;
  color: #121212;
  line-height: 1.6;
}
.page-wrap {
  max-width: 1440px;
  margin: 0 auto;
  padding: 0 1.5rem 4rem;
}
.masthead {
  text-align: center;
  padding: 1.4rem 0 0;
  margin-bottom: 2rem;
}
.masthead-rules {
  border-top: 3px solid #121212;
  border-bottom: 1px solid #121212;
  padding: 1rem 0 0.8rem;
}
.masthead h1 {
  font-size: 2.4rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  font-family: "Georgia", serif;
  line-height: 1.15;
}
.masthead .nav {
  margin-top: 0.65rem;
  font-family: "Helvetica Neue", Arial, sans-serif;
  font-size: 0.7rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #6f6f6f;
}
.masthead .nav a {
  color: #6f6f6f;
  text-decoration: none;
  margin: 0 0.7rem;
}
.masthead .nav a:hover { color: #121212; }
.masthead .nav .active { color: #121212; font-weight: 700; margin: 0 0.7rem; }
.masthead .nav .sep { color: #ccc; }
.masthead .meta {
  font-size: 0.68rem;
  color: #6f6f6f;
  margin-top: 0.55rem;
  padding-bottom: 0.6rem;
  font-family: "Helvetica Neue", Arial, sans-serif;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.masthead-bottom-rule {
  border-top: 1px solid #121212;
  margin-bottom: 0;
}
.columns {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0;
  align-items: start;
  border-top: 1px solid #e2e2e2;
  padding-top: 1.5rem;
  margin-top: 1.5rem;
}
.columns > div {
  min-width: 0;
  overflow-wrap: break-word;
  word-break: break-word;
  padding: 0 2rem;
  border-right: 1px solid #e2e2e2;
}
.columns > div:first-child { padding-left: 0; }
.columns > div:last-child { border-right: none; padding-right: 0; }
@media (max-width: 960px) {
  .columns { grid-template-columns: repeat(2, 1fr); }
  .columns > div:nth-child(2) { border-right: none; padding-right: 0; }
  .columns > div:nth-child(3) { padding-left: 0; border-right: none; border-top: 1px solid #e2e2e2; padding-top: 1.5rem; margin-top: 0.5rem; }
}
@media (max-width: 600px) {
  .columns { grid-template-columns: 1fr; }
  .columns > div { border-right: none; padding: 0; border-top: 1px solid #e2e2e2; padding-top: 1.2rem; margin-top: 0.5rem; }
  .columns > div:first-child { border-top: none; padding-top: 0; margin-top: 0; }
}
.section { margin-bottom: 2.5rem; }
.section-header {
  margin-bottom: 1.2rem;
  padding-bottom: 0.45rem;
  border-bottom: 2px solid #121212;
}
.section-header h2 {
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  font-family: "Helvetica Neue", Arial, sans-serif;
  color: #121212;
}
.section-header .en-label { display: none; }
.entry {
  border-bottom: 1px solid #e2e2e2;
  padding: 0.85rem 0;
}
.entry:last-child { border-bottom: none; }
.entry-title {
  font-size: 1.02rem;
  font-weight: 700;
  color: #121212;
  margin-bottom: 0.2rem;
  font-family: "Georgia", serif;
  line-height: 1.35;
}
.entry-title a { color: inherit; text-decoration: none; }
.entry-title a:hover { text-decoration: underline; }
.entry-summary {
  font-size: 0.85rem;
  color: #333;
  line-height: 1.6;
  font-family: "Helvetica Neue", Arial, sans-serif;
  margin-top: 0.2rem;
}
.entry-meta {
  font-size: 0.67rem;
  color: #6f6f6f;
  margin-top: 0.35rem;
  font-family: "Helvetica Neue", Arial, sans-serif;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}
.entry-source-tag {
  font-weight: 700;
  color: #6f6f6f;
  margin-right: 0.3rem;
}
.entry-source-tag::after { content: " ·"; font-weight: 400; }
.no-articles {
  font-size: 0.85rem;
  color: #999;
  font-style: italic;
  padding: 0.5rem 0;
  font-family: "Helvetica Neue", Arial, sans-serif;
}
.footer {
  text-align: center;
  font-size: 0.67rem;
  color: #bbb;
  border-top: 1px solid #e2e2e2;
  padding-top: 1.5rem;
  margin-top: 3rem;
  font-family: "Helvetica Neue", Arial, sans-serif;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
"""


def esc(s):
    return htmllib.escape(str(s or ""), quote=True)


def render_entry(entry):
    title = esc(clean_text(entry.get("title", ""), max_chars=200))
    link = esc(entry.get("link", "#") or "#")
    summary = esc(clean_text(entry.get("summary", "") or entry.get("description", ""), max_chars=250))
    date = esc(get_date(entry))
    src = esc(getattr(entry, "_source_name", ""))

    source_tag = f'<span class="entry-source-tag">{src}</span>' if src else ""

    return f"""
    <div class="entry">
      <div class="entry-title"><a href="{link}" target="_blank">{title}</a></div>
      <div class="entry-summary">{summary}</div>
      <div class="entry-meta">{source_tag}{date}</div>
    </div>"""


def render_column(col_cfg, data_dict, max_articles=20):
    label = esc(col_cfg["label"])

    all_entries = []
    for src in col_cfg["sources"]:
        all_entries.extend(data_dict.get(src["name"], []))
    sorted_entries = sorted(all_entries, key=sort_key, reverse=True)[:max_articles]

    parts = [f"""
  <div class="section">
    <div class="section-header"><h2>{label}</h2></div>"""]

    if sorted_entries:
        for e in sorted_entries:
            parts.append(render_entry(e))
    else:
        parts.append('    <p class="no-articles">暂无内容</p>')

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
<title>Russia Intelligence Digest · {date_str}</title>
<style>
{CSS}
</style>
</head>
<body>
<div class="page-wrap">
  <div class="masthead">
    <div class="masthead-rules">
      <h1>Russia Intelligence Digest</h1>
      <div class="nav">
        <a href="/china-digest/">China</a>
        <span class="sep">/</span>
        <a href="/china-digest/dprk/">North Korea</a>
        <span class="sep">/</span>
        <span class="active">Russia</span>
      </div>
      <div class="meta">{date_str} &nbsp;·&nbsp; Auto-generated</div>
    </div>
    <div class="masthead-bottom-rule"></div>
  </div>
  <div class="columns">
{col1_html}
{col2_html}
{col3_html}
  </div>
  <div class="footer">
    Auto-generated · Content sourced from RSS feeds · For reference only
  </div>
</div>
</body>
</html>"""

# ============================================================
# 主入口
# ============================================================

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    docs_dir = Path(__file__).parent / "docs" / "russia"
    docs_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n生成 Russia {today} 日报...\n", file=sys.stderr)

    print("【第一栏 · 外媒报道 俄朝关系】", file=sys.stderr)
    col1_data = fetch_column(COLUMN_1)

    print("\n【第二栏 · 俄媒报道 朝鲜】", file=sys.stderr)
    col2_data = fetch_column(COLUMN_2)

    print("\n【第三栏 · 俄媒报道 中国】", file=sys.stderr)
    col3_data = fetch_column(COLUMN_3)

    html_content = render_html(col1_data, col2_data, col3_data, today)

    out = docs_dir / "index.html"
    out.write_text(html_content, encoding="utf-8")
    print(f"\n✅ 已生成：{out}", file=sys.stderr)


if __name__ == "__main__":
    main()
