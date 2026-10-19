#!/usr/bin/env python3
"""把仓库里已入库的报告生成静态阅读站点，兼容电脑、手机与墨水屏阅读器。

输入：reports/index.json（由 tools/reports_index.py 生成）、投资炼丹/、实盘记录/ 下已纳入 Git 的 Markdown。
输出：site/ 目录，纯 HTML，无框架；按公司、专题、时间、类型、公众号发表五个维度建索引，另有站内搜索与 RSS。

用法：python3 tools/build_site.py [--out site]
依赖：markdown、pypinyin（pip install markdown pypinyin）
"""
import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import quote

import markdown
from pypinyin import Style, lazy_pinyin

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_URL = "https://github.com/xbtlin/ai-berkshire"
SITE_NAME = "AI Berkshire 研究阅读"
FRONT = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.S)
H1 = re.compile(r"^#\s+(.+?)\s*$", re.M)
DATE8 = re.compile(r"(20[2-3]\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])")
ASSET_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf", ".csv", ".json", ".txt", ".html"}
TYPE_ORDER = ["深度系列", "研究", "财报", "估值仓位", "组织管理", "横评对比", "公众号", "筛选", "底稿"]
NOISE_BUCKETS = {"筛选池"}


def sh(args):
    return subprocess.check_output(args, cwd=ROOT).decode("utf-8", "replace")


def tracked(prefix):
    out = subprocess.check_output(["git", "ls-files", "-z", "--", prefix], cwd=ROOT)
    return [p for p in out.decode("utf-8", "replace").split("\0") if p]


def page_id(path):
    return hashlib.sha1(path.encode("utf-8")).hexdigest()[:12]


def slug(name):
    s = re.sub(r"[^0-9A-Za-z一-鿿]+", "-", name).strip("-")
    return s or page_id(name)


def initial(name):
    c = name.strip()[:1]
    if not c:
        return "#"
    if re.match(r"[A-Za-z]", c):
        return c.upper()
    if re.match(r"[一-鿿]", c):
        return lazy_pinyin(c, style=Style.FIRST_LETTER)[0].upper()
    return "#"


def read(path):
    full = os.path.join(ROOT, path)
    if os.path.isfile(full):
        with open(full, encoding="utf-8", errors="replace") as f:
            return f.read()
    return blob(path).decode("utf-8", "replace")


def blob(path):
    """读取已入库内容；本地工作区缺失（例如他处未提交的删除）时回退到 HEAD。"""
    return subprocess.check_output(["git", "show", "HEAD:%s" % path], cwd=ROOT,
                                   stderr=subprocess.DEVNULL)


def available(path):
    if os.path.isfile(os.path.join(ROOT, path)):
        return True
    try:
        blob(path)
        return True
    except subprocess.CalledProcessError:
        return False


# ---------- 收集条目 ----------

def collect():
    items = []
    idx = json.load(open(os.path.join(ROOT, "reports", "index.json"), encoding="utf-8"))
    for r in idx["reports"]:
        if not available(r["path"]):
            continue
        items.append({
            "title": r["title"], "path": r["path"], "bucket": r["bucket"], "group": r["group"],
            "series": r.get("series", ""), "type": r.get("type", "研究"), "date": r.get("date", ""),
        })
    seen = {i["path"] for i in items}
    dir_meta = {}
    for i in items:
        dir_meta.setdefault(os.path.dirname(i["path"]), (i["bucket"], i["group"]))
    for p in tracked("reports/"):
        if not p.endswith("README.md") or p in seen or "/_index/" in p:
            continue
        d = os.path.dirname(p)
        bucket, group = dir_meta.get(d, (None, None))
        while bucket is None and d.count("/") > 0:
            d = os.path.dirname(d)
            bucket, group = dir_meta.get(d, (None, None))
        if bucket is None:
            parts = p.split("/")
            bucket, group = ("专题", parts[1] if len(parts) > 2 else "研究总览")
        text = read(p)
        m = H1.search(FRONT.sub("", text))
        items.append({"title": (m.group(1).strip() if m else "%s 导读" % group), "path": p,
                      "bucket": bucket, "group": group, "series": "", "type": "导读",
                      "date": git_date(p)})
    for p in tracked("筛选公司/"):
        if not p.endswith(".md"):
            continue
        parts = p.split("/")
        group = parts[1] if len(parts) > 2 else "筛选公司"
        text = read(p)
        m = H1.search(FRONT.sub("", text))
        name = os.path.basename(p)[:-3]
        dm = DATE8.search(name)
        items.append({"title": m.group(1).strip() if m else name, "path": p, "bucket": "筛选池",
                      "group": group, "series": "", "type": "筛选",
                      "date": "%s-%s-%s" % dm.groups() if dm else git_date(p)})
    for p in tracked("docs/"):
        if not p.endswith(".md") or os.path.basename(p) in ("ROADMAP.md", "README.md"):
            continue
        text = read(p)
        m = H1.search(FRONT.sub("", text))
        items.append({"title": m.group(1).strip() if m else os.path.basename(p)[:-3], "path": p,
                      "bucket": "专题", "group": "随笔与综述", "series": "", "type": "研究",
                      "date": git_date(p)})
    for p in tracked("投资炼丹/"):
        if not p.endswith(".md") or p.endswith("README.md"):
            continue
        parts = p.split("/")
        group = parts[1] if len(parts) > 2 else "其他"
        text = read(p)
        m = H1.search(FRONT.sub("", text))
        name = os.path.basename(p)[:-3]
        dm = DATE8.match(name)
        date = "%s-%s-%s" % dm.groups() if dm else ""
        title = m.group(1).strip() if m else re.sub(r"^\d{8}-", "", name).replace("-", " ")
        pub = re.search(r"发表标题：(.+)", text)
        if pub:
            title = pub.group(1).strip()
        items.append({"title": title, "path": p, "bucket": "公众号发表", "group": group,
                      "series": "", "type": "公众号", "date": date})
    for p in tracked("实盘记录/"):
        if not p.endswith(".md"):
            continue
        text = read(p)
        m = H1.search(FRONT.sub("", text))
        name = os.path.basename(p)[:-3]
        dm = DATE8.search(name)
        date = "%s-%s-%s" % dm.groups() if dm else git_date(p)
        items.append({"title": m.group(1).strip() if m else name, "path": p, "bucket": "实盘记录",
                      "group": "实盘记录", "series": "", "type": "实盘", "date": date})
    for it in items:
        it["id"] = page_id(it["path"])
        it["url"] = "r/%s.html" % it["id"]
    items.sort(key=lambda x: (x["date"] or "0000"), reverse=True)
    return items


# ---------- 内容筛选：只上成品，不上中间产物 ----------
# 中间产物（审计、核验、证据、底稿、数据收集、搜索日志、自动扫描、召回池分视角稿等）仍保留在 GitHub，
# 阅读站点只收录成品报告。被排除的页面若被正文引用，链接自动指向 GitHub 原文。
MID_DIR = re.compile(r"/(evidence|证据|research|data|sources|audit[^/]*|审计[^/]*|[^/]*审读[^/]*|[^/]*核验[^/]*|[^/]*证据)/", re.I)
MID_NAME = re.compile(
    r"审计|审查|审读|审阅|评审|核验|复核|校验|核对|对账|核查|自查|底稿|证据|来源登记|来源与|勘误|修订记录|"
    r"data[_-]?collection|数据收集|search[-_]?log|sources|todo|笔记|素材|financial[-_]rigor|^计算|财务表$|readme__|__readme|"
    r"工作稿|草稿|draft|抽检|待.{0,4}复核", re.I)
POOL_PERSPECTIVE = re.compile(r"/0[1-4]-[^/]*视角\.md$")
BOTTLENECK_RUN = re.compile(r"^reports/bottleneck-map/(20\d\d-\d\d-\d\d|daily)/")


def exclude_reason(it):
    path, name, title = it["path"], os.path.basename(it["path"]), it["title"]
    if BOTTLENECK_RUN.match(path):
        return "自动扫描与日报"
    if MID_DIR.search("/" + path):
        return "证据/审计/调研目录"
    if MID_NAME.search(name[:-3]) or MID_NAME.search(title):
        return "审计核验底稿"
    if it["type"] == "底稿" and "系列说明" not in title:
        return "审计核验底稿"
    if it["bucket"] == "筛选池" and POOL_PERSPECTIVE.search(path):
        return "召回池分视角稿"
    if path in ("reports/README.md",) or path.startswith("reports/_index/"):
        return "索引页"
    if it["bucket"] == "筛选池" and name == "README.md" and path.count("/") > 2:
        return "召回池分视角稿"
    if it["type"] == "导读" and it.get("_size", 9999) < 600:
        return "过短"
    if it.get("_size", 9999) < 800:
        return "过短"
    return ""


def curate(items):
    # 公众号：有发表版（投资炼丹）的，隐藏 reports/ 里对应的原稿，避免同文两份
    drafts = set()
    for it in items:
        if it["bucket"] == "公众号发表":
            m = re.search(r"原稿：\[[^\]]*\]\(([^)]+)\)", read(it["path"]))
            if m:
                drafts.add(os.path.normpath(os.path.join(os.path.dirname(it["path"]), m.group(1))))
    kept, dropped = [], defaultdict(int)
    for it in items:
        it["_size"] = len(read(it["path"]).encode("utf-8"))
        why = "已有公众号发表版" if it["path"] in drafts else exclude_reason(it)
        if why:
            dropped[why] += 1
        else:
            kept.append(it)
    # 去重：内容完全相同的只留一份；同目录同标题的多个版本只留最新最长的一份
    seen_hash, best = {}, {}
    for it in sorted(kept, key=lambda x: (x["date"] or "", x["_size"]), reverse=True):
        h = hashlib.sha1(read(it["path"]).encode("utf-8")).hexdigest()
        key = (os.path.dirname(it["path"]), re.sub(r"\s+", "", it["title"]))
        if h in seen_hash or key in best:
            dropped["重复或旧版本"] += 1
            continue
        seen_hash[h] = 1
        best[key] = it
    kept = [it for it in kept if best.get((os.path.dirname(it["path"]), re.sub(r"\s+", "", it["title"]))) is it]
    for it in kept:
        if it["type"] == "底稿":
            it["type"] = "导读"
    print("收录 %d 篇；排除 %d 篇：%s" % (len(kept), sum(dropped.values()),
          "，".join("%s %d" % kv for kv in sorted(dropped.items(), key=lambda x: -x[1]))))
    return kept


def git_date(path):
    try:
        out = sh(["git", "log", "-1", "--format=%cs", "--", path]).strip()
        return out
    except subprocess.CalledProcessError:
        return ""


# ---------- HTML 外壳 ----------

CSS = """
:root{--bg:#fbfbf9;--card:#fff;--fg:#1f2328;--muted:#656d76;--line:#e3e4e2;--accent:#0b5cad;--accent-bg:#eaf2fb;
--th:#f3f4f2;--code:#f3f4f2;--shadow:0 1px 2px rgba(0,0,0,.05);--radius:10px;--w:46rem;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme]){--bg:#15171a;--card:#1c1f23;--fg:#e6e6e3;--muted:#9aa1a9;
--line:#2d3136;--accent:#6cb0ff;--accent-bg:#1d2a3a;--th:#23272c;--code:#23272c;--shadow:none;color-scheme:dark}}
:root[data-theme=dark]{--bg:#15171a;--card:#1c1f23;--fg:#e6e6e3;--muted:#9aa1a9;--line:#2d3136;--accent:#6cb0ff;
--accent-bg:#1d2a3a;--th:#23272c;--code:#23272c;--shadow:none;color-scheme:dark}
html{font-size:17px;-webkit-text-size-adjust:100%}
html[data-size=s1]{font-size:15px}html[data-size=s3]{font-size:19px}html[data-size=s4]{font-size:22px}
*{box-sizing:border-box}
body{margin:0;color:var(--fg);background:var(--bg);line-height:1.8;
font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Noto Sans CJK SC","Source Han Sans SC","Microsoft YaHei",sans-serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
header.top{position:sticky;top:0;z-index:10;background:color-mix(in srgb,var(--bg) 88%,transparent);
-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
.bar{max-width:72rem;margin:0 auto;padding:0 1rem;display:flex;align-items:center;gap:1rem;height:3.2rem}
.brand{font-weight:700;color:var(--fg);white-space:nowrap}
nav.main{display:flex;gap:.2rem;overflow-x:auto;scrollbar-width:none;flex:1;min-width:0}nav.main::-webkit-scrollbar{display:none}
nav.main a{color:var(--fg);padding:.3rem .65rem;border-radius:6px;white-space:nowrap;font-size:.93rem}
nav.main a:hover,nav.main a.on{background:var(--accent-bg);color:var(--accent);text-decoration:none}
.tools{display:flex;gap:.3rem;white-space:nowrap;flex-shrink:0}
.tools button{font:inherit;font-size:.82rem;color:var(--fg);background:var(--card);border:1px solid var(--line);
border-radius:6px;padding:.15rem .5rem;cursor:pointer}
.tools select{font:inherit;font-size:.82rem;color:var(--fg);background:var(--card);border:1px solid var(--line);border-radius:6px;padding:.1rem .3rem}
main{max-width:var(--w);margin:0 auto;padding:0 1rem 3rem;overflow-wrap:anywhere}
main.wide{max-width:72rem}
.crumb{font-size:.82rem;color:var(--muted);margin:1.2rem 0 0}.crumb a{color:var(--muted)}
h1{font-size:1.75rem;line-height:1.35;margin:.8rem 0 .5rem;letter-spacing:.01em}
h2{font-size:1.3rem;line-height:1.45;margin:2.2rem 0 .8rem;padding-bottom:.3rem;border-bottom:1px solid var(--line)}
h3{font-size:1.08rem;margin:1.6rem 0 .5rem}
.meta{color:var(--muted);font-size:.84rem;margin:.15rem 0 1rem}
ul.list{list-style:none;padding:0;margin:0;background:var(--card);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow)}
ul.list li{padding:.75rem 1rem;border-bottom:1px solid var(--line)}ul.list li:last-child{border-bottom:0}
ul.list li:hover{background:var(--accent-bg)}
ul.list li>a{display:block;color:var(--fg);font-weight:500}ul.list li>a:hover{color:var(--accent);text-decoration:none}
ul.list .meta{margin:.15rem 0 0}
.grid{display:flex;flex-wrap:wrap;gap:.5rem;margin:.6rem 0}
.grid a.btn{display:inline-block;background:var(--card);border:1px solid var(--line);border-radius:999px;padding:.35rem .9rem;
color:var(--fg);font-size:.92rem;box-shadow:var(--shadow)}
.grid a.btn:hover{border-color:var(--accent);color:var(--accent);text-decoration:none}
.hero>.grid:first-of-type a.btn{border-radius:var(--radius);padding:.7rem 1.1rem;font-weight:600}
.idx{display:grid;grid-template-columns:repeat(auto-fill,minmax(15rem,1fr));gap:0}
.idx li{border-bottom:1px solid var(--line)!important}
article{font-size:1.02rem}
article p{margin:.9rem 0}
article a{text-decoration:underline;text-underline-offset:3px;text-decoration-thickness:1px}
.table-wrap{overflow-x:auto;margin:1.2rem 0;border:1px solid var(--line);border-radius:var(--radius);background:var(--card)}
table{border-collapse:collapse;font-size:.86rem;line-height:1.5;min-width:100%}
th,td{border-bottom:1px solid var(--line);padding:.45rem .7rem;vertical-align:top;text-align:left}
th{background:var(--th);font-weight:600;white-space:nowrap}
tbody tr:nth-child(even){background:color-mix(in srgb,var(--th) 45%,transparent)}
blockquote{border-left:3px solid var(--accent);margin:1.2rem 0;padding:.2rem 1rem;color:var(--muted);background:var(--card)}
pre{overflow-x:auto;background:var(--code);border-radius:8px;padding:.8rem;font-size:.82rem;line-height:1.5}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.88em;background:var(--code);padding:.1em .3em;border-radius:4px}
pre code{background:none;padding:0}
img{max-width:100%;height:auto;border-radius:6px}
hr{border:0;border-top:1px solid var(--line);margin:2rem 0}
details.toc{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:.2rem 1rem;margin:1rem 0}
summary{cursor:pointer;padding:.5rem 0;font-weight:600}
.toc ul{padding-left:1.1rem;margin:.2rem 0 .6rem;font-size:.9rem;line-height:1.7}
.toc a{color:var(--fg)}
.layout{display:block}
aside.side{display:none}
@media (min-width:1180px){main.doc{max-width:72rem}.layout{display:grid;grid-template-columns:minmax(0,46rem) 15rem;gap:3rem;justify-content:center}
aside.side{display:block}aside.side .toc{position:sticky;top:4.5rem;max-height:calc(100vh - 6rem);overflow:auto;font-size:.85rem;
border-left:1px solid var(--line);padding-left:1rem}aside.side .toc ul{padding-left:.8rem}
details.toc{display:none}}
.progress{position:fixed;top:0;left:0;height:3px;width:0;background:var(--accent);z-index:11}
footer{max-width:72rem;margin:3rem auto 0;padding:1.2rem 1rem 2rem;border-top:1px solid var(--line);font-size:.82rem;color:var(--muted)}
footer a{color:var(--muted);text-decoration:underline}
input.q{font:inherit;font-size:1.05rem;width:100%;padding:.7rem 1rem;border:1px solid var(--line);border-radius:var(--radius);
background:var(--card);color:var(--fg);outline:none}input.q:focus{border-color:var(--accent)}
@media (max-width:640px){html{font-size:16px}h1{font-size:1.45rem}.bar{gap:.5rem;padding:0 .6rem}.brand{display:none}
.tools .lbl{display:none}ul.list li{padding:.7rem .8rem}}
"""

PREF_JS = """
(function(){var h=document.documentElement,g=function(k){try{return localStorage.getItem(k)}catch(e){return null}};
var t=g('aib-theme'),s=g('aib-size');
if(t&&t!=='auto')h.setAttribute('data-theme',t);if(s)h.setAttribute('data-size',s);
var sz=['s1','','s3','s4'];
window.aibSize=function(d){var c=h.getAttribute('data-size')||'',i=sz.indexOf(c);i=Math.max(0,Math.min(3,i+d));
if(sz[i])h.setAttribute('data-size',sz[i]);else h.removeAttribute('data-size');try{localStorage.setItem('aib-size',sz[i])}catch(e){}};
window.aibTheme=function(v){if(v==='auto')h.removeAttribute('data-theme');else h.setAttribute('data-theme',v);
try{localStorage.setItem('aib-theme',v)}catch(e){}};
document.addEventListener('DOMContentLoaded',function(){var sel=document.getElementById('theme');
if(sel)sel.value=h.getAttribute('data-theme')||'auto';var bar=document.querySelector('.progress');
if(bar){var f=function(){var d=document.documentElement,m=d.scrollHeight-d.clientHeight;bar.style.width=(m>0?d.scrollTop/m*100:0)+'%'};
addEventListener('scroll',f,{passive:true});f()}});})();
"""

NAV = [("index.html", "首页"), ("companies/index.html", "公司"), ("topics/index.html", "专题"),
       ("dates/index.html", "时间"), ("types/index.html", "类型"), ("wechat/index.html", "公众号"),
       ("search.html", "搜索")]


def shell(title, body, depth, crumb="", section="", main_class="", progress=False):
    rel = "../" * depth
    links = "".join('<a href="%s%s"%s>%s</a>' % (rel, u, ' class="on"' if t == section else "", t) for u, t in NAV)
    head = (
        '<header class="top"><div class="bar"><a class="brand" href="{r}index.html">AI Berkshire</a>'
        '<nav class="main">{links}</nav><div class="tools">'
        '<button onclick="aibSize(-1)" title="缩小字号">A−</button><button onclick="aibSize(1)" title="放大字号">A+</button>'
        '<select id="theme" onchange="aibTheme(this.value)" title="外观"><option value="auto">自动</option>'
        '<option value="light">浅色</option><option value="dark">深色</option></select>'
        '</div></div></header>'
    ).format(r=rel, links=links)
    crumb_html = '<div class="crumb">%s</div>' % crumb if crumb else ""
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="theme-color" content="#fbfbf9">'
        '<title>%s · %s</title><link rel="stylesheet" href="%sstyle.css">'
        '<link rel="alternate" type="application/rss+xml" title="%s" href="%sfeed.xml">'
        '<script>%s</script></head><body>%s%s<main class="%s">%s%s</main>'
        '<footer>%s ｜ <a href="%s">GitHub 仓库</a> ｜ <a href="%sfeed.xml">RSS 订阅</a> ｜ 生成于 %s</footer></body></html>'
    ) % (html.escape(title), SITE_NAME, rel, SITE_NAME, rel, PREF_JS,
         '<div class="progress"></div>' if progress else "", head, main_class, crumb_html, body,
         SITE_NAME, REPO_URL, rel, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))


def li(it, depth, show_group=True):
    rel = "../" * depth
    bits = [it["date"] or "日期不详"]
    if show_group and it["group"]:
        bits.append(it["group"])
    if it["type"]:
        bits.append(it["type"])
    return '<li><a href="%s%s">%s</a><div class="meta">%s</div></li>' % (
        rel, it["url"], html.escape(it["title"]), " · ".join(html.escape(b) for b in bits))


def ul(items, depth, show_group=True, limit=None):
    rows = items if limit is None else items[:limit]
    return '<ul class="list">%s</ul>' % "".join(li(i, depth, show_group) for i in rows)


# ---------- Markdown → HTML ----------

LINK_ATTR = re.compile(r'(href|src)="([^"]+)"')


def convert(it, by_path, out_dir):
    text = FRONT.sub("", read(it["path"]))
    m1 = H1.search(text)
    if m1 and (m1.start() < 1500 or m1.group(1).strip() == it["title"]):
        text = text[:m1.start()] + text[m1.end():]
    md = markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists", "toc"],
                           extension_configs={"toc": {"toc_depth": "2-3"}})
    body = md.convert(text)
    base = os.path.dirname(it["path"])
    missing = []

    def fix(m):
        attr, url = m.group(1), m.group(2)
        if re.match(r"^(https?:|mailto:|#|data:)", url):
            return m.group(0)
        clean = url.split("#")[0].split("?")[0]
        target = os.path.normpath(os.path.join(base, clean)).replace("\\", "/")
        if target in by_path:
            return '%s="../%s"' % (attr, by_path[target]["url"])
        ext = os.path.splitext(target)[1].lower()
        src = os.path.join(ROOT, target)
        if ext in ASSET_EXT and available(target):
            dst = os.path.join(out_dir, "files", target)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if not os.path.exists(dst):
                if os.path.isfile(src):
                    shutil.copy2(src, dst)
                else:
                    with open(dst, "wb") as fh:
                        fh.write(blob(target))
            return '%s="../files/%s"' % (attr, quote(target))
        if available(target):
            return '%s="%s/blob/main/%s"' % (attr, REPO_URL, quote(target))
        missing.append(url)
        return m.group(0)

    body = LINK_ATTR.sub(fix, body)
    body = body.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")
    toc = md.toc if md.toc and md.toc.count("<li>") >= 3 else ""
    return body, toc


# ---------- 各类页面 ----------

def write(out_dir, rel_path, content):
    p = os.path.join(out_dir, rel_path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)


def build(out_dir):
    items = curate(collect())
    by_path = {i["path"]: i for i in items}
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)
    write(out_dir, "style.css", CSS)
    write(out_dir, ".nojekyll", "")

    companies = defaultdict(list)
    topics = defaultdict(list)
    screens = defaultdict(list)
    wechat = defaultdict(list)
    months = defaultdict(list)
    types = defaultdict(list)
    for it in items:
        if it["bucket"] == "公司":
            companies[it["group"]].append(it)
        elif it["bucket"] == "公众号发表":
            wechat[it["group"]].append(it)
            companies[it["group"]].append(it)
        elif it["bucket"] == "筛选池":
            screens[it["group"]].append(it)
        elif it["bucket"] == "实盘记录":
            topics["实盘记录"].append(it)
        else:
            topics[it["group"]].append(it)
        if it["date"]:
            months[it["date"][:7]].append(it)
        types[it["type"]].append(it)

    comp_url = {c: "companies/%s/index.html" % slug(c) for c in companies}
    topic_url = {t: "topics/%s/index.html" % slug(t) for t in topics}
    screen_url = {s: "screens/%s/index.html" % slug(s) for s in screens}

    def group_link(it, depth):
        rel = "../" * depth
        if it["bucket"] in ("公司", "公众号发表") and it["group"] in comp_url:
            return '<a href="%s%s">%s</a>' % (rel, comp_url[it["group"]], html.escape(it["group"]))
        if it["bucket"] == "筛选池" and it["group"] in screen_url:
            return '<a href="%s%s">%s</a>' % (rel, screen_url[it["group"]], html.escape(it["group"]))
        g = "实盘记录" if it["bucket"] == "实盘记录" else it["group"]
        if g in topic_url:
            return '<a href="%s%s">%s</a>' % (rel, topic_url[g], html.escape(g))
        return html.escape(g)

    # 报告页
    for it in items:
        body, toc = convert(it, by_path, out_dir)
        same = [x for x in (companies.get(it["group"]) or topics.get(it["group"]) or screens.get(it["group"]) or [])
                if x["id"] != it["id"]][:12]
        meta = " · ".join(x for x in [it["date"], it["type"]] if x)
        head = "<h1>%s</h1><div class=\"meta\">%s ｜ %s ｜ <a href=\"%s/blob/main/%s\">GitHub 原文</a></div>" % (
            html.escape(it["title"]), group_link(it, 1), html.escape(meta), REPO_URL, quote(it["path"]))
        if toc:
            head += '<details class="toc"><summary>目录</summary>%s</details>' % toc
        tail = ""
        if same:
            tail = "<h2>同一专题的其他报告</h2>" + ul(same, 1, show_group=False)
        crumb = '<a href="../index.html">首页</a> › %s' % group_link(it, 1)
        side = '<aside class="side"><div class="toc"><div class="meta">本文目录</div>%s</div></aside>' % toc if toc else "<aside class=\"side\"></aside>"
        page = '<div class="layout"><div>%s<article>%s</article>%s</div>%s</div>' % (head, body, tail, side)
        write(out_dir, it["url"], shell(it["title"], page, 1, crumb, main_class="doc", progress=True))

    # 公司索引与公司页
    def company_page(name, rows):
        groups = defaultdict(list)
        for r in rows:
            key = "公众号发表" if r["bucket"] == "公众号发表" else r["type"]
            groups[key].append(r)
        order = ["导读", "公众号发表"] + TYPE_ORDER
        parts = ["<h1>%s</h1><div class=\"meta\">共 %d 篇，最近更新 %s</div>" % (
            html.escape(name), len(rows), rows[0]["date"] if rows and rows[0]["date"] else "—")]
        for k in order + [k for k in groups if k not in order]:
            if k in groups:
                parts.append("<h2>%s（%d）</h2>%s" % (html.escape(k), len(groups[k]), ul(groups[k], 2, show_group=False)))
        return "".join(parts)

    for c, rows in companies.items():
        write(out_dir, comp_url[c], shell(c, company_page(c, rows), 2,
                                          '<a href="../../index.html">首页</a> › <a href="../index.html">公司</a>'))
    letters = defaultdict(list)
    for c in companies:
        letters[initial(c)].append(c)
    top = sorted(companies, key=lambda c: -len(companies[c]))[:24]
    body = "<h1>按公司</h1><div class=\"meta\">%d 家公司，%d 篇报告</div><h2>报告最多的公司</h2><div class=\"grid\">%s</div>" % (
        len(companies), sum(len(v) for v in companies.values()),
        "".join('<a class="btn" href="../%s">%s %d</a>' % (comp_url[c], html.escape(c), len(companies[c])) for c in top))
    body += "<h2>全部公司（按拼音首字母）</h2>"
    for L in sorted(letters):
        names = sorted(letters[L], key=lambda c: lazy_pinyin(c))
        body += "<h3>%s</h3><ul class=\"list idx\">%s</ul>" % (L, "".join(
            '<li><a href="../%s">%s</a><div class="meta">%d 篇 · 最近 %s</div></li>' % (
                comp_url[c], html.escape(c), len(companies[c]), companies[c][0]["date"] or "—") for c in names))
    write(out_dir, "companies/index.html", shell("按公司", body, 1, section="公司"))

    # 专题
    def simple_group_page(name, rows, depth, crumb):
        by_series = defaultdict(list)
        for r in rows:
            by_series[r["series"] or ""].append(r)
        parts = ["<h1>%s</h1><div class=\"meta\">共 %d 篇</div>" % (html.escape(name), len(rows))]
        if len(by_series) > 1:
            for s in sorted(by_series, key=lambda s: (s == "", s), reverse=True):
                parts.append("<h2>%s（%d）</h2>%s" % (html.escape(s or "主报告"), len(by_series[s]), ul(by_series[s], depth, show_group=False)))
        else:
            parts.append(ul(rows, depth, show_group=False))
        return shell(name, "".join(parts), depth, crumb)

    for t, rows in topics.items():
        write(out_dir, topic_url[t], simple_group_page(t, rows, 2, '<a href="../../index.html">首页</a> › <a href="../index.html">专题</a>'))
    for s, rows in screens.items():
        write(out_dir, screen_url[s], simple_group_page(s, rows, 2, '<a href="../../index.html">首页</a> › <a href="../../topics/index.html">专题</a>'))
    tnames = sorted(topics, key=lambda t: topics[t][0]["date"] or "", reverse=True)
    body = "<h1>专题与横评</h1><ul class=\"list\">%s</ul>" % "".join(
        '<li><a href="../%s">%s</a><div class="meta">%d 篇 · 最近 %s</div></li>' % (
            topic_url[t], html.escape(t), len(topics[t]), topics[t][0]["date"] or "—") for t in tnames)
    body += "<h2>筛选池与召回池</h2><ul class=\"list\">%s</ul>" % "".join(
        '<li><a href="../%s">%s</a><div class="meta">%d 篇 · 最近 %s</div></li>' % (
            screen_url[s], html.escape(s), len(screens[s]), screens[s][0]["date"] or "—")
        for s in sorted(screens, key=lambda s: screens[s][0]["date"] or "", reverse=True))
    write(out_dir, "topics/index.html", shell("专题", body, 1, section="专题"))

    # 时间
    years = defaultdict(list)
    for m in months:
        years[m[:4]].append(m)
    body = "<h1>按时间</h1>"
    for y in sorted(years, reverse=True):
        body += "<h2>%s 年</h2><div class=\"grid\">%s</div>" % (y, "".join(
            '<a class="btn" href="%s.html">%s 月 %d</a>' % (m, int(m[5:]), len(months[m])) for m in sorted(years[y], reverse=True)))
    write(out_dir, "dates/index.html", shell("按时间", body, 1, section="时间"))
    for m, rows in months.items():
        main = [r for r in rows if r["bucket"] not in NOISE_BUCKETS]
        noise = [r for r in rows if r["bucket"] in NOISE_BUCKETS]
        body = "<h1>%s 年 %d 月</h1><div class=\"meta\">%d 篇</div>%s" % (m[:4], int(m[5:]), len(rows), ul(main, 1))
        if noise:
            body += "<details><summary>筛选池与召回池日报（%d）</summary>%s</details>" % (len(noise), ul(noise, 1))
        write(out_dir, "dates/%s.html" % m, shell("%s 年 %d 月" % (m[:4], int(m[5:])), body, 1,
                                                   '<a href="../index.html">首页</a> › <a href="index.html">时间</a>'))

    # 类型
    tlist = [t for t in TYPE_ORDER if t in types] + [t for t in types if t not in TYPE_ORDER]
    body = "<h1>按类型</h1><div class=\"grid\">%s</div>" % "".join(
        '<a class="btn" href="%s.html">%s %d</a>' % (slug(t), html.escape(t), len(types[t])) for t in tlist)
    write(out_dir, "types/index.html", shell("按类型", body, 1, section="类型"))
    for t in tlist:
        rows = types[t]
        main = [r for r in rows if r["bucket"] not in NOISE_BUCKETS]
        noise = [r for r in rows if r["bucket"] in NOISE_BUCKETS]
        body = "<h1>%s</h1><div class=\"meta\">%d 篇</div>%s" % (html.escape(t), len(rows), ul(main, 1))
        if noise:
            body += "<details><summary>筛选池与召回池（%d）</summary>%s</details>" % (len(noise), ul(noise, 1))
        write(out_dir, "types/%s.html" % slug(t), shell(t, body, 1, '<a href="../index.html">首页</a> › <a href="index.html">类型</a>'))

    # 公众号发表
    wrows = sorted((r for rows in wechat.values() for r in rows), key=lambda r: r["date"], reverse=True)
    body = "<h1>公众号发表版</h1><div class=\"meta\">%d 篇，正文为公众号发表版本</div>%s" % (len(wrows), ul(wrows, 1))
    write(out_dir, "wechat/index.html", shell("公众号", body, 1, section="公众号"))

    # 搜索
    sdata = [{"t": i["title"], "g": i["group"], "k": i["type"], "d": i["date"], "u": i["url"]} for i in items]
    write(out_dir, "search.json", json.dumps(sdata, ensure_ascii=False, separators=(",", ":")))
    body = ("<h1>搜索</h1><p>输入公司名、关键词或日期（如 2026-09），按标题、公司、类型匹配。</p>"
            '<input class="q" id="q" type="search" placeholder="例如：拼多多 财报" autofocus>'
            '<div class="meta" id="n"></div><ul class="list" id="out"></ul>'
            "<script>var D=null;function esc(s){return s.replace(/[&<>\"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]})}"
            "function run(){var q=document.getElementById('q').value.trim().toLowerCase();var out=document.getElementById('out'),n=document.getElementById('n');"
            "if(!q){out.innerHTML='';n.textContent='';return}var ws=q.split(/\\s+/);var r=D.filter(function(x){var s=(x.t+' '+x.g+' '+x.k+' '+x.d).toLowerCase();return ws.every(function(w){return s.indexOf(w)>=0})});"
            "n.textContent='共 '+r.length+' 条'+(r.length>200?'，只显示前 200 条':'');out.innerHTML=r.slice(0,200).map(function(x){return '<li><a href=\"'+x.u+'\">'+esc(x.t)+'</a><div class=\"meta\">'+esc([x.d,x.g,x.k].filter(Boolean).join(' · '))+'</div></li>'}).join('')}"
            "fetch('search.json').then(function(r){return r.json()}).then(function(d){D=d;document.getElementById('q').addEventListener('input',run);run()});</script>")
    write(out_dir, "search.html", shell("搜索", body, 0, section="搜索"))

    # 首页
    recent, per_group = [], defaultdict(int)
    for i in items:
        if i["bucket"] in NOISE_BUCKETS or i["type"] == "底稿" or i["series"] == "evidence":
            continue
        if per_group[i["group"]] >= 2:
            continue
        per_group[i["group"]] += 1
        recent.append(i)
        if len(recent) >= 30:
            break
    body = "<h1>%s</h1><p class=\"meta\">%d 篇报告 · %d 家公司 · 最近更新 %s</p>" % (
        SITE_NAME, len(items), len(companies), items[0]["date"] if items else "—")
    body += "<div class=\"grid\">%s</div>" % "".join(
        '<a class="btn" href="%s">%s</a>' % (u, t) for u, t in [
            ("companies/index.html", "按公司"), ("topics/index.html", "专题与横评"), ("dates/index.html", "按时间"),
            ("types/index.html", "按类型"), ("wechat/index.html", "公众号发表版"), ("search.html", "搜索")])
    body += "<h2>最近更新</h2>" + ul(recent, 0)
    body += "<h2>报告最多的公司</h2><div class=\"grid\">%s</div>" % "".join(
        '<a class="btn" href="%s">%s %d</a>' % (comp_url[c], html.escape(c), len(companies[c])) for c in top[:16])
    write(out_dir, "index.html", shell("首页", '<div class="hero">' + body + "</div>", 0, section="首页"))
    write(out_dir, "404.html", shell("没有这一页", "<h1>没有这一页</h1><p><a href=\"index.html\">回首页</a></p>", 0))

    # RSS
    feed_items = [i for i in items if i["bucket"] not in NOISE_BUCKETS][:50]
    base = "https://xbtlin.github.io/ai-berkshire/"
    rss = ['<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel><title>%s</title><link>%s</link><description>投资研究报告</description>' % (SITE_NAME, base)]
    for i in feed_items:
        rss.append("<item><title>%s</title><link>%s%s</link><guid>%s%s</guid><pubDate>%s</pubDate><description>%s</description></item>" % (
            html.escape(i["title"]), base, i["url"], base, i["url"],
            datetime.strptime(i["date"], "%Y-%m-%d").strftime("%a, %d %b %Y 00:00:00 +0000") if i["date"] else "",
            html.escape(" · ".join(x for x in [i["group"], i["type"]] if x))))
    rss.append("</channel></rss>")
    write(out_dir, "feed.xml", "".join(rss))

    print("生成 %d 篇报告页，%d 家公司，%d 个专题，%d 个月份 -> %s" % (len(items), len(companies), len(topics) + len(screens), len(months), out_dir))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "site"))
    args = ap.parse_args()
    build(args.out)
