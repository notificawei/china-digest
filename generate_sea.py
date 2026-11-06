#!/usr/bin/env python3
"""
东南亚 · 日本情报内参 · 自动生成脚本
每日抓取 RSS，聚焦环境 / AI，渲染为报纸风格 HTML，输出到 docs/sea/index.html
覆盖：印尼 · 马来西亚 · 新加坡 · 泰国 · 老挝 · 柬埔寨 · 日本
"""

import feedparser
import requests
import html as htmllib
import sys
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ============================================================
# RSS 来源配置
# ============================================================

COLUMN_1 = {
    "label": "🌏 区域综合",
    "en_label": "Regional Media",
    "sources": [
        {
            "name": "Channel News Asia",
            "url": "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=10416",
            "require_sea": True,
        },
        {
            "name": "Nikkei Asia",
            "url": "https://asia.nikkei.com/rss/feed/nar",
            "require_sea": True,
        },
        {
            "name": "The Diplomat",
            "url": "https://thediplomat.com/feed/",
            "require_sea": True,
        },
        {
            "name": "Eco-Business",
            "url": "https://www.eco-business.com/feed/",
            "require_sea": True,
        },
        {
            "name": "Rest of World",
            "url": "https://restofworld.org/feed/latest",
            "require_sea": True,
        },
        {
            "name": "Al Jazeera",
            "url": "https://www.aljazeera.com/xml/rss/all.xml",
            "require_sea": True,
        },
        {
            "name": "BBC Asia",
            "url": "https://feeds.bbci.co.uk/news/world/asia/rss.xml",
            "require_sea": True,
        },
        {
            "name": "NYT Asia Pacific",
            "url": "https://rss.nytimes.com/services/xml/rss/nyt/AsiaPacific.xml",
            "require_sea": True,
        },
        {
            "name": "Financial Times",
            "url": "https://www.ft.com/world/asia-pacific?format=rss",
            "require_sea": True,
        },
    ],
}

COLUMN_2 = {
    "label": "🗺️ 国别媒体",
    "en_label": "Country Press",
    "sources": [
        # 日本
        {
            "name": "Japan Times",
            "url": "https://www.japantimes.co.jp/feed/",
            "require_sea": False,  # 已是日本媒体
        },
        {
            "name": "NHK World",
            "url": "https://www3.nhk.or.jp/nhkworld/en/news/feeds/",
            "require_sea": False,
        },
        {
            "name": "Japan Today",
            "url": "https://japantoday.com/feed",
            "require_sea": False,
        },
        {
            "name": "The Mainichi",
            "url": "https://mainichi.jp/english/rss/etc/english.rss",
            "require_sea": False,
        },
        # 印尼
        {
            "name": "Jakarta Post",
            "url": "https://www.thejakartapost.com/feed",
            "require_sea": False,
        },
        {
            "name": "Tempo English",
            "url": "https://en.tempo.co/rss/feed.xml",
            "require_sea": False,
        },
        {
            "name": "Coconuts Jakarta",
            "url": "https://coconuts.co/jakarta/feed/",
            "require_sea": False,
        },
        # 泰国
        {
            "name": "Bangkok Post",
            "url": "https://www.bangkokpost.com/rss/data/topstories.xml",
            "require_sea": False,
        },
        {
            "name": "The Nation Thailand",
            "url": "https://www.nationthailand.com/rss.xml",
            "require_sea": False,
        },
        {
            "name": "Coconuts Bangkok",
            "url": "https://coconuts.co/bangkok/feed/",
            "require_sea": False,
        },
        # 马来西亚
        {
            "name": "Free Malaysia Today",
            "url": "https://www.freemalaysiatoday.com/feed/",
            "require_sea": False,
        },
        {
            "name": "Malaysiakini",
            "url": "https://www.malaysiakini.com/rss",
            "require_sea": False,
        },
        {
            "name": "The Star Malaysia",
            "url": "https://www.thestar.com.my/rss/News/Nation/",
            "require_sea": False,
        },
        # 新加坡
        {
            "name": "Today Online",
            "url": "https://www.todayonline.com/feed",
            "require_sea": False,
        },
        # 柬埔寨
        {
            "name": "Khmer Times",
            "url": "https://www.khmertimeskh.com/feed/",
            "require_sea": False,
        },
        {
            "name": "Phnom Penh Post",
            "url": "https://www.phnompenhpost.com/feed",
            "require_sea": False,
        },
        # 老挝
        {
            "name": "Laotian Times",
            "url": "https://laotiantimes.com/feed/",
            "require_sea": False,
        },
        {
            "name": "RFA Laos",
            "url": "https://www.rfa.org/english/news/laos/rss2.xml",
            "require_sea": False,
        },
    ],
}

COLUMN_3 = {
    "label": "🌿 环境 · 气候",
    "en_label": "Environment & Climate",
    "sources": [
        {
            "name": "Mongabay",
            "url": "https://news.mongabay.com/feed/",
            "require_sea": True,
        },
        {
            "name": "Climate Home News",
            "url": "https://www.climatechangenews.com/feed/",
            "require_sea": True,
        },
        {
            "name": "The Third Pole",
            "url": "https://www.thethirdpole.net/en/feed/",
            "require_sea": True,
        },
        {
            "name": "Eco-Business (env)",
            "url": "https://www.eco-business.com/feed/",
            "require_sea": False,  # 已聚焦亚洲环境
        },
        {
            "name": "Channel News Asia (env)",
            "url": "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=10416",
            "require_sea": True,
            "require_env": True,
        },
    ],
}

# ============================================================
# 关键词
# ============================================================

# 地理过滤：含以下任一词 → 通过 require_sea 检查
SEA_KEYWORDS = [
    "indonesia", "indonesian", "jakarta", "bali", "surabaya",
    "malaysia", "malaysian", "kuala lumpur",
    "singapore", "singaporean",
    "thailand", "thai", "bangkok",
    "laos", "lao", "vientiane",
    "cambodia", "cambodian", "phnom penh", "khmer",
    "japan", "japanese", "tokyo", "osaka",
    "southeast asia", "south-east asia", "asean", "mekong",
    "philippines", "philippine", "manila",
    "vietnam", "vietnamese", "hanoi",
    "myanmar", "burma",
    "brunei", "timor",
]

# 环境过滤：含以下任一词 → 通过 require_env 检查
ENV_KEYWORDS = [
    "climate", "environment", "deforestation", "forest", "carbon", "emission",
    "flooding", "flood", "haze", "pollution", "biodiversity", "coral", "ocean",
    "palm oil", "logging", "conservation", "wildlife", "plastic", "waste",
    "renewable", "solar", "clean energy", "net zero", "sustainability",
    "typhoon", "cyclone", "drought", "wildfire", "peatland", "mangrove",
]

# 第四栏聚合白名单（环境 + AI + 科技）
SEA_FOCUS_WHITELIST = [
    # 环境 / 气候
    "climate", "environment", "deforestation", "forest", "carbon", "emission",
    "flood", "haze", "pollution", "biodiversity", "coral", "ocean",
    "palm oil", "logging", "conservation", "wildlife", "plastic",
    "renewable", "solar", "clean energy", "net zero", "sustainability",
    "typhoon", "cyclone", "drought", "wildfire", "peatland", "mangrove",
    # AI / 科技
    "artificial intelligence", "ai ", " ai", "machine learning", "algorithm",
    "automation", "startup", "fintech", "digital", "platform",
    "tech", "chatgpt", "llm", "data center", "semiconductor",
    "app", "e-commerce", "ride-hailing", "grab", "gojek",
]

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
    raw = re.sub(r"<[^>]+>", " ", str(raw))
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


def text_contains(text, keywords):
    low = text.lower()
    return any(kw.lower() in low for kw in keywords)


def passes_filter(entry, source_cfg):
    title = clean_text(getattr(entry, "title", "") or "", max_chars=500)
    summary = clean_text(
        getattr(entry, "summary", "") or getattr(entry, "description", "") or "",
        max_chars=500,
    )
    full_text = title + " " + summary

    if source_cfg.get("require_sea"):
        if not text_contains(full_text, SEA_KEYWORDS):
            return False

    if source_cfg.get("require_env"):
        if not text_contains(full_text, ENV_KEYWORDS):
            return False

    return True


def is_focus_worthy(entry):
    title = clean_text(getattr(entry, "title", "") or "", max_chars=500)
    summary = clean_text(
        getattr(entry, "summary", "") or getattr(entry, "description", "") or "",
        max_chars=500,
    )
    full_text = (title + " " + summary).lower()
    return any(kw.lower() in full_text for kw in SEA_FOCUS_WHITELIST)


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
    for entry in feed.entries[:60]:
        if not passes_filter(entry, source_cfg):
            continue
        entry._source_name = name
        results.append(entry)

    print(f"  ✓ {name}: {len(results)} 条", file=sys.stderr)
    return results


def fetch_column(col_cfg):
    data = {}
    for src in col_cfg["sources"]:
        data[src["name"]] = fetch_source(src)
    return data


# ============================================================
# HTML
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
.col-highlight .section-header { border-bottom-color: #1a7a3c; }
.col-highlight .section-header h2 { color: #1a7a3c; }
.entry { border-bottom: 1px solid #e2e2e2; padding: 0.85rem 0; }
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
.entry-source-tag { font-weight: 700; color: #6f6f6f; margin-right: 0.3rem; }
.entry-source-tag::after { content: " ·"; font-weight: 400; }
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

NAV = """
        <a href="/china-digest/">China</a>
        <span class="sep">/</span>
        <a href="/china-digest/dprk/">North Korea</a>
        <span class="sep">/</span>
        <a href="/china-digest/russia/">Russia</a>
        <span class="sep">/</span>
        <span class="active">Southeast Asia</span>
"""


def esc(s):
    return htmllib.escape(str(s or ""), quote=True)


def render_entry(entry, show_source_tag=False):
    title = esc(clean_text(getattr(entry, "title", "") or "", max_chars=200))
    link = esc(getattr(entry, "link", "#") or "#")
    summary = esc(
        clean_text(
            getattr(entry, "summary", "") or getattr(entry, "description", "") or "",
            max_chars=250,
        )
    )
    date = esc(get_date(entry))
    source_name = esc(getattr(entry, "_source_name", ""))

    source_tag = ""
    if show_source_tag and source_name:
        source_tag = f'<span class="entry-source-tag">{source_name}</span>'

    return f"""
  <div class="entry">
    <div class="entry-title"><a href="{link}" target="_blank" rel="noopener">{title}</a></div>
    <div class="entry-summary">{summary}</div>
    <div class="entry-meta">{source_tag}{date}</div>
  </div>"""


def render_column(col_cfg, data_dict, col_class="", max_articles=25):
    label = esc(col_cfg["label"])
    en_label = esc(col_cfg["en_label"])

    all_entries = []
    for src in col_cfg["sources"]:
        all_entries.extend(data_dict.get(src["name"], []))
    all_entries.sort(key=sort_key, reverse=True)

    parts = [f"""  <div class="section {col_class}">
    <div class="section-header">
      <h2>{label} <span class="en-label">{en_label}</span></h2>
    </div>"""]

    if all_entries:
        for e in all_entries[:max_articles]:
            parts.append(render_entry(e, show_source_tag=True))
    else:
        parts.append('    <p class="no-articles">暂无内容</p>')

    parts.append("  </div>")
    return "\n".join(parts)


def render_focus_col(focus_entries):
    parts = ["""  <div class="section col-highlight">
    <div class="section-header">
      <h2>🔥 重点议题 <span class="en-label">Environment · AI · Tech</span></h2>
    </div>"""]

    if focus_entries:
        for e in focus_entries[:20]:
            parts.append(render_entry(e, show_source_tag=True))
    else:
        parts.append('    <p class="no-articles">暂无符合条件的文章</p>')

    parts.append("  </div>")
    return "\n".join(parts)


def render_html(col1_data, col2_data, col3_data, focus_entries, date_str):
    col1_html = render_column(COLUMN_1, col1_data)
    col2_html = render_column(COLUMN_2, col2_data)
    col3_html = render_column(COLUMN_3, col3_data)
    col4_html = render_focus_col(focus_entries)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Southeast Asia Digest · {date_str}</title>
<style>
{CSS}
</style>
</head>
<body>
<div class="page-wrap">
  <div class="masthead">
    <div class="masthead-rules">
      <h1>China Intelligence Digest</h1>
      <div class="nav">{NAV}</div>
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
    docs_dir = Path(__file__).parent / "docs" / "sea"
    docs_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n生成 SEA {today} 日报...\n", file=sys.stderr)

    print("【第一栏 · 区域综合】", file=sys.stderr)
    col1_data = fetch_column(COLUMN_1)

    print("\n【第二栏 · 国别媒体】", file=sys.stderr)
    col2_data = fetch_column(COLUMN_2)

    print("\n【第三栏 · 环境·气候】", file=sys.stderr)
    col3_data = fetch_column(COLUMN_3)

    # 第四栏：从所有来源聚合，按环境+AI关键词过滤，每源最多3条
    print("\n【第四栏 · 重点议题聚合】", file=sys.stderr)
    all_entries = []
    for data in [col1_data, col2_data, col3_data]:
        for entries in data.values():
            all_entries.extend(entries)

    all_entries.sort(key=sort_key, reverse=True)

    seen_links = set()
    per_source_count = {}
    focus_entries = []

    for e in all_entries:
        if not is_focus_worthy(e):
            continue
        link = getattr(e, "link", "#")
        if link in seen_links:
            continue
        source = getattr(e, "_source_name", "")
        if per_source_count.get(source, 0) >= 3:
            continue
        seen_links.add(link)
        per_source_count[source] = per_source_count.get(source, 0) + 1
        focus_entries.append(e)

    print(f"  → 聚合 {len(focus_entries)} 条重点议题（每源最多 3 条）", file=sys.stderr)

    html_content = render_html(col1_data, col2_data, col3_data, focus_entries, today)

    out = docs_dir / "index.html"
    out.write_text(html_content, encoding="utf-8")
    print(f"\n✅ 已生成：{out}", file=sys.stderr)
    print(str(out))


if __name__ == "__main__":
    main()
