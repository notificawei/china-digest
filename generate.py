#!/usr/bin/env python3
"""
中国社会情报内参 · 自动生成脚本
每日抓取 RSS / Substack，过滤无关内容，渲染为报纸风格 HTML。

用法：
    python3 generate.py              # 生成到 ./output/YYYY-MM-DD.html
    python3 generate.py --test       # 只测试 RSS 连通性，不生成 HTML
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
# filter 字段：
#   "cn_official"  → 过滤掉含官员/党政关键词的文章
#   "en_geo"       → 过滤掉含外交地缘政治关键词的文章（需同时含"China"才保留）
#   "none"         → 不过滤
#
# ⚠️  标有 [需验证] 的 URL 是最佳猜测，请运行 --test 确认后替换。

COLUMN_1 = {
    "label": "外媒报道",
    "en_label": "International Press",
    "sources": [
        {
            "name": "Sixth Tone",
            "url": "https://www.sixthtone.com/rss/",
            "lang": "en",
            "filter": "none",
        },
        {
            "name": "SCMP",
            "url": "https://www.scmp.com/rss/2/feed",
            "lang": "en",
            "filter": "none",                   # 已是中国专栏，不额外过滤
        },
        {
            "name": "Rest of World",
            "url": "https://restofworld.org/feed/latest",
            "lang": "en",
            "filter": "none",
            "require_china": True,
        },
        {
            "name": "MIT Technology Review",
            "url": "https://www.technologyreview.com/feed/",
            "lang": "en",
            "filter": "none",
            "require_china": True,
        },
        {
            "name": "Washington Post",
            "url": "https://feeds.washingtonpost.com/rss/world",
            "lang": "en",
            "filter": "none",
            "require_china": True,
        },
        {
            "name": "Wall Street Journal",
            "url": "https://feeds.content.dowjones.io/public/rss/RSSWorldNews",
            "lang": "en",
            "filter": "none",
            "require_china": True,
        },
        {
            "name": "Wired",
            "url": "https://www.wired.com/feed/rss",
            "lang": "en",
            "filter": "none",
            "require_china": True,
        },
    ],
}


COLUMN_3 = {
    "label": "独立记者 Newsletter",
    "en_label": "Independent Journalists",
    "sources": [
        # Substack RSS 格式：https://{slug}.substack.com/feed
        # 打开对应 Substack 页面，URL 中的用户名即为 slug
        {
            "name": "田间",
            "url": "https://tianjiancmp.substack.com/feed",
            "lang": "zh",
            "filter": "none",
        },
        {
            "name": "水瓶纪元",
            "url": "https://aquarianhq.substack.com/feed",
            "lang": "zh",
            "filter": "none",
        },
        {
            "name": "端传媒",
            "url": "https://theinitium.com/rss/",
            "lang": "zh",
            "filter": "none",
        },
        {
            "name": "报道者",
            "url": "https://www.twreporter.org/a/rss2.xml",
            "lang": "zh",
            "filter": "none",
        },
    ],
}

# ============================================================
# 过滤关键词
# ============================================================

# 中文：含以下任一词 → 丢弃
CN_OFFICIAL_BLACKLIST = [
    "习近平", "总书记", "政治局", "中央委员会", "中央全会",
    "省委书记", "市委书记", "县委书记", "党委书记",
    "重要指示", "重要批示", "作出重要",
    "国务院", "人民代表大会", "政协",
    "中央纪委", "纪检监察",
]

# 英文：含以下任一词 → 丢弃
EN_GEO_BLACKLIST = [
    "sanctions", "diplomatic", "bilateral", "multilateral",
    "state department", "foreign policy", "trade war",
    "geopolitical", "geopolitics", "tariffs", "pentagon",
    "nato", "g7", "g20", "united nations", "security council",
]

# 第四栏：含以下任一词 → 收录
COLUMN_4_WHITELIST = [
    # AI / 科技
    "人工智能", "ai", "算法", "大模型", "自动化", "机器人", "数字化",
    "短视频", "直播", "平台", "互联网",
    # 经济 / 就业
    "失业", "裁员", "降薪", "消费降级", "降级", "债务",
    "倒闭", "破产", "欠薪", "拖欠",
    "就业", "找工作", "应届生", "毕业生", "求职",
    "灵活就业", "外卖", "骑手", "工厂", "工人", "打工",
    "生计", "民生", "收入", "贫困",
    # 英文对应词
    "artificial intelligence", "algorithm", "automation",
    "layoff", "unemployment", "job", "worker", "labor",
    "income", "poverty", "gig economy", "delivery",
]

# ============================================================
# 工具函数
# ============================================================

def get_text(entry, field):
    """从 feedparser entry 取纯文本，剥离 HTML 标签并解码 HTML 实体"""
    val = getattr(entry, field, "") or ""
    if hasattr(val, "value"):
        val = val.value
    # 剥离 HTML 标签
    val = re.sub(r"<[^>]+>", " ", val)
    # 解码 HTML 实体（&amp; &#x20; 等）
    val = htmllib.unescape(val)
    val = re.sub(r"\s+", " ", val).strip()
    return val


def get_title(entry):
    return get_text(entry, "title")


def get_summary(entry, max_chars=220):
    s = get_text(entry, "summary") or get_text(entry, "description")
    if len(s) > max_chars:
        s = s[:max_chars].rsplit(" ", 1)[0] + "…"
    return s


def get_link(entry):
    return getattr(entry, "link", "#") or "#"


def get_date(entry):
    # 1. 尝试已解析的时间结构
    for field in ("published_parsed", "updated_parsed"):
        t = getattr(entry, field, None)
        if t:
            try:
                dt = datetime(*t[:6], tzinfo=timezone.utc)
                return dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
    # 2. 尝试原始字符串字段
    for field in ("published", "updated", "dc_date"):
        raw = getattr(entry, field, None)
        if raw:
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(raw)
                return dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
            # ISO 8601 格式
            try:
                raw_clean = raw[:19]
                dt = datetime.strptime(raw_clean, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                return dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
    return ""


def text_contains(text, keywords):
    """大小写不敏感，text 中是否含 keywords 中任一词"""
    low = text.lower()
    return any(kw.lower() in low for kw in keywords)


def passes_filter(entry, source_cfg):
    """返回 True 表示文章通过过滤，可以展示"""
    title = get_title(entry)
    summary = get_summary(entry, max_chars=500)
    full_text = title + " " + summary

    # require_china 对任何 filter 类型都生效
    if source_cfg.get("require_china"):
        if not text_contains(full_text, ["china", "chinese", "beijing", "shanghai", "中国"]):
            return False

    ftype = source_cfg.get("filter", "none")

    if ftype == "cn_official":
        if text_contains(full_text, CN_OFFICIAL_BLACKLIST):
            return False

    elif ftype == "en_geo":
        if text_contains(full_text, EN_GEO_BLACKLIST):
            return False

    return True


def is_col4_worthy(entry):
    """判断是否应出现在第四栏（AI / 经济 / 就业）"""
    title = get_title(entry)
    summary = get_summary(entry, max_chars=500)
    full_text = (title + " " + summary).lower()
    return any(kw.lower() in full_text for kw in COLUMN_4_WHITELIST)


# ============================================================
# 抓取 RSS
# ============================================================

CUTOFF_DAYS = 7  # 只展示最近 N 天的文章


HEADERS_DEFAULT = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}
HEADERS_FEEDFETCHER = {
    "User-Agent": "Feedfetcher-Google; (+http://www.google.com/feedfetcher.html)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


def fetch_source(source_cfg):
    """抓取单个 RSS 源，返回过滤后的 entry 列表"""
    url = source_cfg["url"]
    name = source_cfg["name"]
    ua = HEADERS_FEEDFETCHER if source_cfg.get("ua") == "feedfetcher" else HEADERS_DEFAULT
    try:
        resp = requests.get(url, headers=ua, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        if feed.bozo and not feed.entries:
            print(f"  ⚠️  {name}: feed 格式异常 ({url})", file=sys.stderr)
            return []
    except Exception as e:
        print(f"  ❌ {name}: {e}", file=sys.stderr)
        return []

    results = []
    for entry in feed.entries[:40]:  # 每源最多扫 40 条
        if not passes_filter(entry, source_cfg):
            continue
        entry._source_name = name
        results.append(entry)

    print(f"  ✓  {name}: {len(results)} 条", file=sys.stderr)
    return results


def fetch_column(col_cfg):
    """抓取整列的所有来源"""
    all_entries = {}  # source_name → [entries]
    for src in col_cfg["sources"]:
        entries = fetch_source(src)
        all_entries[src["name"]] = entries
    return all_entries


# ============================================================
# HTML 渲染
# ============================================================

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: "Georgia", "Times New Roman", "宋体", serif;
  background: #f9f7f2;
  color: #1a1a1a;
  line-height: 1.7;
}
.page-wrap {
  max-width: 1440px;
  margin: 0 auto;
  padding: 2.5rem 1.5rem 4rem;
}
.columns {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 2rem;
  align-items: start;
}
.columns > div {
  min-width: 0;
  overflow-wrap: break-word;
  word-break: break-word;
}
@media (max-width: 900px) { .columns { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 600px) { .columns { grid-template-columns: 1fr; } }
.masthead {
  text-align: center;
  border-top: 3px solid #1a1a1a;
  border-bottom: 3px solid #1a1a1a;
  padding: 1.2rem 0;
  margin-bottom: 2.5rem;
}
.masthead h1 { font-size: 2rem; font-weight: 700; letter-spacing: 0.08em; }
.masthead .meta {
  font-size: 0.82rem; color: #666; margin-top: 0.4rem;
  font-family: "Helvetica Neue", Arial, sans-serif;
  letter-spacing: 0.05em;
}
.section { margin-bottom: 2.8rem; }
.section-header {
  display: flex; align-items: baseline; gap: 0.8rem;
  border-bottom: 1.5px solid #1a1a1a;
  padding-bottom: 0.4rem; margin-bottom: 1.4rem;
}
.section-header h2 { font-size: 1.15rem; font-weight: 700; letter-spacing: 0.04em; }
.section-header .en-label {
  font-size: 0.75rem; color: #888;
  font-family: "Helvetica Neue", Arial, sans-serif;
  text-transform: uppercase; letter-spacing: 0.08em;
}
/* 第四栏高亮 */
.col-highlight .section-header { border-bottom-color: #c0392b; }
.col-highlight .section-header h2 { color: #c0392b; }
.source-label {
  font-size: 0.72rem;
  font-family: "Helvetica Neue", Arial, sans-serif;
  text-transform: uppercase; letter-spacing: 0.1em; color: #888;
  border-left: 2px solid #ccc; padding-left: 0.5rem;
  margin: 1.4rem 0 0.8rem;
}
.entry { border-bottom: 0.5px solid #ddd; padding: 0.9rem 0; }
.entry:last-child { border-bottom: none; }
.entry-title {
  font-size: 1rem; font-weight: 700; color: #1a1a1a;
  margin-bottom: 0.15rem; font-family: "Georgia", serif;
}
.entry-title a { color: inherit; text-decoration: none; }
.entry-title a:hover { text-decoration: underline; }
.entry-summary {
  font-size: 0.88rem; color: #444; line-height: 1.65;
  font-family: "Helvetica Neue", Arial, sans-serif;
}
.entry-meta {
  font-size: 0.75rem; color: #999; margin-top: 0.4rem;
  font-family: "Helvetica Neue", Arial, sans-serif;
}
.entry-source-tag {
  display: inline-block; font-size: 0.68rem; color: #fff;
  background: #888; border-radius: 2px;
  padding: 0 4px; margin-right: 4px; vertical-align: middle;
}
.no-articles {
  font-size: 0.88rem; color: #999; font-style: italic;
  padding: 0.5rem 0;
  font-family: "Helvetica Neue", Arial, sans-serif;
}
.footer {
  text-align: center; font-size: 0.75rem; color: #bbb;
  border-top: 1px solid #ddd; padding-top: 1.5rem; margin-top: 3rem;
  font-family: "Helvetica Neue", Arial, sans-serif; letter-spacing: 0.03em;
}
"""


def esc(s):
    return htmllib.escape(str(s or ""), quote=True)


def render_entry(entry, show_source_tag=False):
    title = esc(get_title(entry))
    link = esc(get_link(entry))
    summary = esc(get_summary(entry))
    date = esc(get_date(entry))
    source_name = esc(getattr(entry, "_source_name", ""))

    source_tag = ""
    if show_source_tag and source_name:
        source_tag = f'<span class="entry-source-tag">{source_name}</span>'

    return f"""
    <div class="entry">
      <div class="entry-title">{source_tag}<a href="{link}" target="_blank">{title}</a></div>
      <div class="entry-summary">{summary}</div>
      <div class="entry-meta">{date}</div>
    </div>"""


def sort_key(entry):
    """返回可排序的日期字符串，无日期的排到最后"""
    d = get_date(entry)
    return d if d else "0000-00-00 00:00"


def render_column(col_cfg, data_dict, col_class=""):
    label = esc(col_cfg["label"])
    en_label = esc(col_cfg["en_label"])

    parts = [f"""
  <div class="section {col_class}">
    <div class="section-header">
      <h2>{label}</h2>
      <span class="en-label">{en_label}</span>
    </div>"""]

    # 合并所有来源，按日期降序排列
    all_entries = []
    for src in col_cfg["sources"]:
        all_entries.extend(data_dict.get(src["name"], []))

    all_entries.sort(key=sort_key, reverse=True)

    if all_entries:
        for e in all_entries[:30]:  # 每栏最多展示 30 条
            parts.append(render_entry(e, show_source_tag=True))
    else:
        parts.append('    <p class="no-articles">暂无内容</p>')

    parts.append("  </div>")
    return "\n".join(parts)


def render_col4(col4_entries):
    """渲染第四栏（从所有来源聚合）"""
    parts = ["""
  <div class="section col-highlight">
    <div class="section-header">
      <h2>🔥 重点议题</h2>
      <span class="en-label">AI · Economy · Employment</span>
    </div>"""]

    if col4_entries:
        for e in col4_entries[:20]:
            parts.append(render_entry(e, show_source_tag=True))
    else:
        parts.append('    <p class="no-articles">暂无符合条件的文章</p>')

    parts.append("  </div>")
    return "\n".join(parts)


def render_html(col1_data, col3_data, col4_entries, date_str):
    col1_html = render_column(COLUMN_1, col1_data)
    col3_html = render_column(COLUMN_3, col3_data)
    col4_html = render_col4(col4_entries)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>中国社会情报内参 · {date_str}</title>
<style>
{CSS}
</style>
</head>
<body>
<div class="page-wrap">
  <div class="masthead">
    <h1>中国社会情报内参</h1>
    <div class="meta">CHINA SOCIAL INTELLIGENCE DIGEST &nbsp;·&nbsp; {date_str} &nbsp;·&nbsp; 自动生成</div>
  </div>
  <div class="columns">
{col1_html}
{col3_html}
{col4_html}
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

def test_mode():
    """只测试各 RSS 源连通性"""
    print("\n=== RSS 连通性测试 ===\n")
    all_cols = [COLUMN_1, COLUMN_3]
    for col in all_cols:
        print(f"【{col['label']}】")
        for src in col["sources"]:
            try:
                ua = HEADERS_FEEDFETCHER if src.get("ua") == "feedfetcher" else HEADERS_DEFAULT
                resp = requests.get(src["url"], headers=ua, timeout=15, allow_redirects=True)
                feed = feedparser.parse(resp.content)
                count = len(feed.entries)
                status = "✓" if count > 0 else "✗"
                note = f"HTTP {resp.status_code}" if count == 0 else ""
            except Exception as e:
                count = 0
                status = "✗"
                note = str(e)[:60]
            print(f"  {status} {src['name']:22s}  {count:3d} 条   {note or src['url']}")
        print()


def main():
    if "--test" in sys.argv:
        test_mode()
        return

    today = datetime.now().strftime("%Y-%m-%d")
    docs_dir = Path(__file__).parent / "docs"
    docs_dir.mkdir(exist_ok=True)
    archive_dir = docs_dir / "archive"
    archive_dir.mkdir(exist_ok=True)

    print(f"\n生成 {today} 日报...\n", file=sys.stderr)

    print("【第一栏 · 外媒报道】", file=sys.stderr)
    col1_data = fetch_column(COLUMN_1)

    print("\n【第二栏 · 独立记者 Newsletter】", file=sys.stderr)
    col3_data = fetch_column(COLUMN_3)

    # 第三栏：从前两栏所有文章里筛 AI/经济/就业
    all_entries = []
    for data in [col1_data, col3_data]:
        for entries in data.values():
            all_entries.extend(entries)

    col4_entries = [e for e in all_entries if is_col4_worthy(e)]
    # 去重（同一文章可能来自多个栏目）
    seen_links = set()
    col4_deduped = []
    for e in col4_entries:
        link = get_link(e)
        if link not in seen_links:
            seen_links.add(link)
            col4_deduped.append(e)

    print(f"\n【第三栏】聚合 {len(col4_deduped)} 条重点议题文章", file=sys.stderr)

    html_content = render_html(col1_data, col3_data, col4_deduped, today)

    # 写入 docs/index.html（GitHub Pages 首页）
    index_path = docs_dir / "index.html"
    index_path.write_text(html_content, encoding="utf-8")

    # 写入 docs/archive/YYYY-MM-DD.html（历史归档）
    archive_path = archive_dir / f"{today}.html"
    archive_path.write_text(html_content, encoding="utf-8")

    print(f"\n✅ 已生成：{index_path}", file=sys.stderr)
    print(str(index_path))


if __name__ == "__main__":
    main()
