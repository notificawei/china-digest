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
from datetime import datetime, timezone, timedelta
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
            "require_dprk": True,
        },
        {
            "name": "Korea Times",
            "url": "https://www.koreatimes.co.kr/www/rss/rss.xml",
            "require_dprk": True,
        },
        {
            "name": "Korea Herald",
            "url": "https://www.koreaherald.com/rss/newsAll",
            "require_dprk": True,
        },
    ],
}

COLUMN_3 = {
    "label": "🌐 国际外媒",
    "en_label": "International Press",
    "sources": [
        # 专题频道（仍需关键词确认，避免偶发无关内容）
        {
            "name": "The Diplomat",
            "url": "https://thediplomat.com/tag/north-korea/feed/",
            "require_dprk": True,
        },
        {
            "name": "The Guardian",
            "url": "https://www.theguardian.com/world/north-korea/rss",
            "require_dprk": True,
        },
        {
            "name": "Straits Times",
            "url": "https://www.straitstimes.com/tags/north-korea/rss.xml",
            "require_dprk": True,
        },
        {
            "name": "RFA",
            "url": "https://www.rfa.org/english/news/korea/rss2.xml",
            "require_dprk": True,
        },
        # 通讯社（Google News RSS 搜全文，仍需 title/summary 二次过滤）
        {
            "name": "AP",
            "url": "https://news.google.com/rss/search?q=north+korea+site:apnews.com&hl=en",
            "require_dprk": True,
        },
        {
            "name": "AFP",
            "url": "https://news.google.com/rss/search?q=north+korea+site:afp.com&hl=en",
            "require_dprk": True,
        },
        {
            "name": "Reuters",
            "url": "https://news.google.com/rss/search?q=north+korea+site:reuters.com&hl=en",
            "require_dprk": True,
        },
        {
            "name": "The Economist",
            "url": "https://news.google.com/rss/search?q=north+korea+site:economist.com&hl=en",
            "require_dprk": True,
        },
        {
            "name": "Financial Times",
            "url": "https://news.google.com/rss/search?q=north+korea+site:ft.com&hl=en",
            "require_dprk": True,
        },
        # 综合频道（过滤朝鲜关键词）
        {
            "name": "BBC",
            "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
            "require_dprk": True,
        },
        {
            "name": "CNN",
            "url": "http://rss.cnn.com/rss/edition_world.rss",
            "require_dprk": True,
        },
        {
            "name": "Washington Post",
            "url": "https://feeds.washingtonpost.com/rss/world",
            "require_dprk": True,
        },
        {
            "name": "NYT",
            "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
            "require_dprk": True,
        },
        {
            "name": "Al Jazeera",
            "url": "https://www.aljazeera.com/xml/rss/all.xml",
            "require_dprk": True,
        },
        {
            "name": "Nikkei Asia",
            "url": "https://asia.nikkei.com/rss/feed/nar",
            "require_dprk": True,
        },
    ],
}

COLUMN_4 = {
    "label": "📢 朝鲜官方",
    "en_label": "DPRK Official Media",
    "sources": [
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


DPRK_KEYWORDS = [
    "north korea", "n. korea", "n.korea", "dprk", "kim jong", "pyongyang",
    "조선", "朝鲜", "korean peninsula", "inter-korean", "denuclearization",
    "choe son hui", "kim yo jong", "korean war", "unification ministry",
    "ministry of unification",
]

def passes_dprk_filter(entry, source_cfg):
    """返回 True 表示文章包含朝鲜相关内容，可以展示"""
    if not source_cfg.get("require_dprk"):
        return True
    title = clean_text(entry.get("title", ""), max_chars=500).lower()
    summary = clean_text(entry.get("summary", "") or entry.get("description", ""), max_chars=500).lower()
    full_text = title + " " + summary
    return any(kw in full_text for kw in DPRK_KEYWORDS)

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
        if not passes_dprk_filter(entry, source_cfg):
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
  font-family: "Georgia", "Times New Roman", "宋体", serif;
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
.masthead .nav a { color: #6f6f6f; text-decoration: none; margin: 0 0.7rem; }
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
.masthead-bottom-rule { border-top: 1px solid #121212; }
.columns {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
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
  padding: 0 1.6rem;
  border-right: 1px solid #e2e2e2;
}
.columns > div:first-child { padding-left: 0; }
.columns > div:last-child { border-right: none; padding-right: 0; }
@media (max-width: 1100px) {
  .columns { grid-template-columns: repeat(2, 1fr); }
  .columns > div:nth-child(2) { border-right: none; padding-right: 0; }
  .columns > div:nth-child(3) { padding-left: 0; border-top: 1px solid #e2e2e2; padding-top: 1.5rem; margin-top: 0.5rem; }
  .columns > div:nth-child(4) { border-right: none; border-top: 1px solid #e2e2e2; padding-top: 1.5rem; margin-top: 0.5rem; }
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
.section-header .en-label {
  display: inline;
  font-size: 0.62rem;
  font-family: "Helvetica Neue", Arial, sans-serif;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #999;
  font-weight: 400;
  margin-left: 0.4rem;
}
.entry { border-bottom: 1px solid #e2e2e2; padding: 0.85rem 0; }
.entry:last-child { border-bottom: none; }
.entry-title-en {
  font-size: 1.02rem;
  font-weight: 700;
  color: #121212;
  margin-bottom: 0.2rem;
  font-family: "Georgia", serif;
  line-height: 1.35;
}
.entry-title-en a { color: inherit; text-decoration: none; }
.entry-title-en a:hover { text-decoration: underline; }
.entry-title-zh { font-size: 0.8rem; color: #888; margin-bottom: 0.3rem; font-style: italic; font-family: "Helvetica Neue", Arial, sans-serif; }
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
.entry-meta .source-tag {
  font-weight: 700;
  color: #6f6f6f;
  margin-right: 0.3rem;
}
.entry-meta .source-tag::after { content: " ·"; font-weight: 400; }
.no-articles { font-size: 0.85rem; color: #999; font-style: italic; padding: 0.5rem 0; font-family: "Helvetica Neue", Arial, sans-serif; }
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
.search-bar {
  padding: 0.7rem 0 0.9rem;
  text-align: center;
  border-bottom: 1px solid #e2e2e2;
  margin-bottom: 0.5rem;
}
.search-bar input {
  width: 100%;
  max-width: 480px;
  padding: 0.45rem 1rem;
  font-size: 0.82rem;
  font-family: "Helvetica Neue", Arial, sans-serif;
  border: 1px solid #ccc;
  border-radius: 2px;
  outline: none;
  color: #121212;
}
.search-bar input:focus { border-color: #121212; }
.entry.search-hidden { display: none; }
.section.search-all-hidden { display: none; }
"""


def esc(s):
    return htmllib.escape(str(s or ""), quote=True)


def render_entry(entry, show_source=False):
    title_en = esc(clean_text(entry.get("title", ""), max_chars=200))
    link = esc(entry.get("link", "#") or "#")
    summary = esc(clean_text(entry.get("summary", "") or entry.get("description", ""), max_chars=250))
    date = esc(get_date(entry))

    title_zh = esc(translate(entry.get("title", "")))
    title_zh_html = f'<div class="entry-title-zh">{title_zh}</div>' if title_zh else ""

    source_tag = ""
    if show_source:
        src_name = esc(getattr(entry, "_source_name", ""))
        if src_name:
            source_tag = f'<span class="source-tag">{src_name}</span>'

    return f"""
    <div class="entry">
      <div class="entry-title-en"><a href="{link}" target="_blank">{title_en}</a></div>
      {title_zh_html}
      <div class="entry-summary">{summary}</div>
      <div class="entry-meta">{source_tag}{date}</div>
    </div>"""


def render_column(col_cfg, data_dict, max_articles=20):
    label = esc(col_cfg["label"])
    en_label = esc(col_cfg["en_label"])

    # 合并所有来源，按时间倒序排列
    all_entries = []
    for src in col_cfg["sources"]:
        all_entries.extend(data_dict.get(src["name"], []))

    sorted_entries = sorted(all_entries, key=sort_key, reverse=True)[:max_articles]

    parts = [f"""
  <div class="section">
    <div class="section-header">
      <h2>{label} <span class="en-label">{en_label}</span></h2>
    </div>"""]

    if sorted_entries:
        for e in sorted_entries:
            parts.append(render_entry(e, show_source=True))
    else:
        parts.append('    <p class="no-articles">暂无文章（抓取失败或无相关内容）</p>')

    parts.append("  </div>")
    return "\n".join(parts)


def render_html(col1_data, col2_data, col3_data, col4_data, date_str):
    col1_html = render_column(COLUMN_1, col1_data)
    col2_html = render_column(COLUMN_2, col2_data)
    col3_html = render_column(COLUMN_3, col3_data)
    col4_html = render_column(COLUMN_4, col4_data)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>North Korea Intelligence Digest · {date_str}</title>
<style>
{CSS}
</style>
</head>
<body>
<div class="page-wrap">
  <div class="masthead">
    <div class="masthead-rules">
      <h1>North Korea Intelligence Digest</h1>
      <div class="nav">
        <a href="/china-digest/">China</a>
        <span class="sep">/</span>
        <span class="active">North Korea</span>
        <span class="sep">/</span>
        <a href="/china-digest/russia/">Russia</a>
      </div>
      <div class="meta">{date_str} &nbsp;·&nbsp; Auto-generated</div>
    </div>
    <div class="masthead-bottom-rule"></div>
  </div>
  <div class="search-bar">
    <input type="text" id="search-input" placeholder="Search articles…" autocomplete="off">
  </div>
  <div class="columns">
{col1_html}
{col2_html}
{col3_html}
{col4_html}
  </div>
  <div class="footer">
    本文件由脚本自动生成 · 内容来自各媒体 RSS · 仅供参考
  </div>
</div>
<script>
(function(){{
  var inp = document.getElementById('search-input');
  if (!inp) return;
  inp.addEventListener('input', function() {{
    var q = this.value.trim().toLowerCase();
    document.querySelectorAll('.entry').forEach(function(e) {{
      var match = !q || e.textContent.toLowerCase().indexOf(q) !== -1;
      e.classList.toggle('search-hidden', !match);
    }});
    document.querySelectorAll('.section').forEach(function(s) {{
      var visible = s.querySelectorAll('.entry:not(.search-hidden)').length;
      s.classList.toggle('search-all-hidden', q.length > 0 && visible === 0);
    }});
  }});
}})();
</script>
</body>
</html>"""

# ============================================================
# 主入口
# ============================================================

def main():
    KST = timezone(timedelta(hours=9))
    today = datetime.now(KST).strftime("%Y-%m-%d")
    docs_dir = Path(__file__).parent / "docs" / "dprk"
    docs_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n生成 DPRK {today} 日报...\n", file=sys.stderr)

    print("【第一栏 · 智库分析】", file=sys.stderr)
    col1_data = fetch_column(COLUMN_1)

    print("\n【第二栏 · 韩国媒体】", file=sys.stderr)
    col2_data = fetch_column(COLUMN_2)

    print("\n【第三栏 · 国际外媒】", file=sys.stderr)
    col3_data = fetch_column(COLUMN_3)

    print("\n【第四栏 · 朝鲜官方】", file=sys.stderr)
    col4_data = fetch_column(COLUMN_4)

    html_content = render_html(col1_data, col2_data, col3_data, col4_data, today)

    out = docs_dir / "index.html"
    out.write_text(html_content, encoding="utf-8")
    print(f"\n✅ 已生成：{out}", file=sys.stderr)


if __name__ == "__main__":
    main()
