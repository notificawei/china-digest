#!/usr/bin/env python3
"""
中国在全球南方 · 自动生成脚本
追踪中国在非洲、拉丁美洲等南方国家的本地影响——
来源全部是当地英文媒体，而非国际媒体转述。
输出到 docs/global-south/index.html

过滤逻辑：
  - 用 Google News site: 搜索锁定当地媒体 + "china"
  - 二次关键词过滤：只保留涉及中国在当地"实体存在"的文章
    （投资/工程/工人/贷款/渔船/矿山……）
  - 排除纯地缘政治/外交峰会报道
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
# 策略：用 Google News RSS 对每家当地媒体做 "china" site: 搜索
# 这样每条结果已经含 "china"，再用二次过滤判断是否涉及本地影响

def gnews(site, extra="china"):
    """生成 Google News RSS URL，搜索特定站点上的 china 相关内容"""
    q = f"{extra}+site:{site}"
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


COLUMN_1 = {
    "label": "🌍 非洲",
    "en_label": "Africa",
    "sources": [
        # 南非
        {"name": "Daily Maverick",    "url": gnews("dailymaverick.co.za")},
        {"name": "Business Day (SA)", "url": gnews("businesslive.co.za")},
        {"name": "Mail & Guardian",   "url": gnews("mg.co.za")},
        # 尼日利亚
        {"name": "Premium Times",     "url": gnews("premiumtimesng.com")},
        {"name": "The Punch",         "url": gnews("punchng.com")},
        # 肯尼亚 / 东非
        {"name": "Daily Nation",      "url": gnews("nation.africa")},
        {"name": "The East African",  "url": gnews("theeastafrican.co.ke")},
        # 坦桑尼亚
        {"name": "The Citizen (TZ)",  "url": gnews("thecitizen.co.tz")},
        # 埃塞俄比亚
        {"name": "The Reporter (ET)", "url": gnews("thereporterethiopia.com")},
        # 津巴布韦
        {"name": "NewsDay Zimbabwe",  "url": gnews("newsday.co.zw")},
        # 赞比亚
        {"name": "Zambia Daily Mail", "url": gnews("daily-mail.co.zm")},
        # 加纳
        {"name": "Daily Graphic",     "url": gnews("graphic.com.gh")},
        # 埃及
        {"name": "Egypt Independent", "url": gnews("egyptindependent.com")},
    ],
}

COLUMN_2 = {
    "label": "🌎 拉丁美洲",
    "en_label": "Latin America",
    "sources": [
        # 区域综合（英文）
        {"name": "Mercopress",           "url": gnews("mercopress.com")},
        {"name": "Rio Times Online",     "url": gnews("riotimesonline.com")},
        {"name": "Buenos Aires Herald",  "url": gnews("buenosairesherald.com")},
        # 墨西哥
        {"name": "Mexico News Daily",    "url": gnews("mexiconewsdaily.com")},
        # 哥伦比亚
        {"name": "Colombia Reports",     "url": gnews("colombiareports.com")},
        # 秘鲁
        {"name": "Peru Reports",         "url": gnews("perureports.com")},
        # 智利
        {"name": "Santiago Times",       "url": gnews("santiagotimes.cl")},
        # 委内瑞拉
        {"name": "Venezuela Analysis",   "url": gnews("venezuelanalysis.com")},
        # 巴拿马 / 中美洲
        {"name": "The Tico Times (CR)",  "url": gnews("ticotimes.net")},
        # 加勒比
        {"name": "Jamaica Observer",     "url": gnews("jamaicaobserver.com")},
        {"name": "Trinidad Guardian",    "url": gnews("guardian.co.tt")},
    ],
}

COLUMN_3 = {
    "label": "🔬 专项追踪",
    "en_label": "Specialist Trackers",
    "sources": [
        # 专门追踪中国在拉美影响的媒体
        {
            "name": "Dialogo Chino",
            "url": "https://dialogochino.net/en/feed/",
            "require_impact": False,  # 本身就是专项媒体，全部收录
        },
        # 专门追踪中国在非洲影响
        {
            "name": "China Africa Project",
            "url": "https://chinaafricaproject.com/feed/",
            "require_impact": False,
        },
        # 中国在全球南方
        {
            "name": "China-Global South Project",
            "url": "https://news.google.com/rss/search?q=site:chinaglobalsouth.com&hl=en-US&gl=US&ceid=US:en",
            "require_impact": False,
        },
        # Belt & Road 专项
        {
            "name": "BRI Observer",
            "url": "https://news.google.com/rss/search?q=belt+and+road+africa+OR+latin+america&hl=en-US&gl=US&ceid=US:en",
            "require_impact": False,
        },
        # Mongabay - 中国在全球南方的环境影响
        {
            "name": "Mongabay (China impact)",
            "url": "https://news.google.com/rss/search?q=china+site:mongabay.com+africa+OR+amazon+OR+latin+america&hl=en-US&gl=US&ceid=US:en",
            "require_impact": False,
        },
        # 中东 / 海湾（非西方大国）
        {
            "name": "Arab News",
            "url": gnews("arabnews.com"),
            "require_impact": True,
        },
        {
            "name": "Gulf Times",
            "url": gnews("gulf-times.com"),
            "require_impact": True,
        },
        # 南亚
        {
            "name": "The Hindu",
            "url": gnews("thehindu.com"),
            "require_impact": True,
        },
        {
            "name": "Dawn (Pakistan)",
            "url": gnews("dawn.com"),
            "require_impact": True,
        },
        {
            "name": "Daily Star (Bangladesh)",
            "url": gnews("thedailystar.net"),
            "require_impact": True,
        },
    ],
}

# ============================================================
# 关键词过滤
# ============================================================

# "中国本地影响"关键词 —— 涉及中国在当地的实体存在
# 文章含以下任一词 → 通过 require_impact 检查
CHINA_IMPACT_KEYWORDS = [
    # 投资 / 工程
    "chinese company", "chinese firm", "chinese investment", "chinese-funded",
    "china-funded", "chinese contractor", "chinese-built", "chinese project",
    "chinese loan", "chinese debt", "chinese bank",
    # 人员 / 移民
    "chinese workers", "chinese nationals", "chinese migrants",
    "chinese businessmen", "chinese community", "chinatown",
    # 资源 / 环境
    "chinese fishing", "chinese trawler", "chinese mine", "chinese mining",
    "chinese logging", "chinese port", "chinese dam",
    # 知名中国企业
    "huawei", "alibaba", "tencent", "byd", "cnooc", "sinopec", "sinohydro",
    "china railway", "china harbour", "china road", "crbc",
    "exim bank", "china development bank", "cdb",
    "bri", "belt and road", "belt & road",
    # 商品 / 经济
    "made in china", "chinese goods", "chinese products", "chinese imports",
    "chinese tourists", "chinese students",
    # 软实力
    "confucius institute", "chinese embassy", "chinese diplomat",
    "chinese military", "chinese navy",
]

# 排除纯外交/地缘政治报道（即使含上述词）
GEOPOLITICAL_BLACKLIST = [
    "g20", "g7", "united nations", "un security council",
    "bilateral talks", "state visit", "diplomatic meeting",
    "foreign minister visit", "xi jinping visit",
    "military exercise", "nuclear",
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

    # 专项媒体跳过二次过滤
    if source_cfg.get("require_impact") is False:
        return True

    # 必须涉及中国本地影响
    if not text_contains(full_text, CHINA_IMPACT_KEYWORDS):
        return False

    # 排除纯外交/峰会报道
    if text_contains(full_text, GEOPOLITICAL_BLACKLIST):
        return False

    return True


def is_highlight_worthy(entry):
    """判断是否进入第四栏（聚合重点）"""
    title = clean_text(getattr(entry, "title", "") or "", max_chars=500)
    summary = clean_text(
        getattr(entry, "summary", "") or getattr(entry, "description", "") or "",
        max_chars=500,
    )
    full_text = (title + " " + summary).lower()
    # 高价值关键词：涉及资源、劳工、债务、环境的本地影响
    highlight_kw = [
        "chinese workers", "chinese loan", "chinese debt", "chinese fishing",
        "chinese mining", "chinese dam", "belt and road", "bri",
        "sinohydro", "china railway", "china harbour",
        "exim bank", "china development bank",
        "chinese logging", "chinese trawler",
        "confucius institute",
    ]
    return any(kw in full_text for kw in highlight_kw)


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
.col-highlight .section-header { border-bottom-color: #c0392b; }
.col-highlight .section-header h2 { color: #c0392b; }
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
        <a href="/china-digest/sea/">Southeast Asia</a>
        <span class="sep">/</span>
        <span class="active">Global South</span>
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


def render_column(col_cfg, data_dict, col_class="", max_articles=25, max_per_source=4):
    label = esc(col_cfg["label"])
    en_label = esc(col_cfg["en_label"])

    all_entries = []
    for src in col_cfg["sources"]:
        all_entries.extend(data_dict.get(src["name"], []))
    all_entries.sort(key=sort_key, reverse=True)

    # 每源限制
    seen_per_src = {}
    capped = []
    for e in all_entries:
        src = getattr(e, "_source_name", "")
        if seen_per_src.get(src, 0) < max_per_source:
            capped.append(e)
            seen_per_src[src] = seen_per_src.get(src, 0) + 1
    all_entries = capped

    parts = [f"""  <div class="section {col_class}">
    <div class="section-header">
      <h2>{label} <span class="en-label">{en_label}</span></h2>
    </div>"""]

    if all_entries:
        for e in all_entries[:max_articles]:
            parts.append(render_entry(e, show_source_tag=True))
    else:
        parts.append('    <p class="no-articles">暂无内容（各来源尚无中国本地影响相关报道）</p>')

    parts.append("  </div>")
    return "\n".join(parts)


def render_highlight_col(highlight_entries):
    parts = ["""  <div class="section col-highlight">
    <div class="section-header">
      <h2>🔥 重点追踪 <span class="en-label">China's Local Footprint</span></h2>
    </div>"""]

    if highlight_entries:
        for e in highlight_entries[:20]:
            parts.append(render_entry(e, show_source_tag=True))
    else:
        parts.append('    <p class="no-articles">暂无符合条件的文章</p>')

    parts.append("  </div>")
    return "\n".join(parts)


def render_html(col1_data, col2_data, col3_data, highlight_entries, date_str):
    col1_html = render_column(COLUMN_1, col1_data)
    col2_html = render_column(COLUMN_2, col2_data)
    col3_html = render_column(COLUMN_3, col3_data, max_per_source=6)
    col4_html = render_highlight_col(highlight_entries)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>China in the Global South · {date_str}</title>
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
    本文件由脚本自动生成 · 内容来自各地本地媒体 RSS · 仅供参考
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
    docs_dir = Path(__file__).parent / "docs" / "global-south"
    docs_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n生成 Global South {today} 日报...\n", file=sys.stderr)

    print("【第一栏 · 非洲】", file=sys.stderr)
    col1_data = fetch_column(COLUMN_1)

    print("\n【第二栏 · 拉丁美洲】", file=sys.stderr)
    col2_data = fetch_column(COLUMN_2)

    print("\n【第三栏 · 专项追踪】", file=sys.stderr)
    col3_data = fetch_column(COLUMN_3)

    # 第四栏：从所有来源聚合高价值文章，每源最多 2 条
    print("\n【第四栏 · 重点追踪聚合】", file=sys.stderr)
    all_entries = []
    for data in [col1_data, col2_data, col3_data]:
        for entries in data.values():
            all_entries.extend(entries)

    all_entries.sort(key=sort_key, reverse=True)

    seen_links = set()
    per_source_count = {}
    highlight_entries = []

    for e in all_entries:
        if not is_highlight_worthy(e):
            continue
        link = getattr(e, "link", "#")
        if link in seen_links:
            continue
        source = getattr(e, "_source_name", "")
        if per_source_count.get(source, 0) >= 2:
            continue
        seen_links.add(link)
        per_source_count[source] = per_source_count.get(source, 0) + 1
        highlight_entries.append(e)

    print(f"  → 聚合 {len(highlight_entries)} 条重点文章", file=sys.stderr)

    html_content = render_html(col1_data, col2_data, col3_data, highlight_entries, today)

    out = docs_dir / "index.html"
    out.write_text(html_content, encoding="utf-8")
    print(f"\n✅ 已生成：{out}", file=sys.stderr)
    print(str(out))


if __name__ == "__main__":
    main()
