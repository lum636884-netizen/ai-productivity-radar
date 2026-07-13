#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布前强制校验（ROUTINE v7 §13）。

用法：python3 scripts/validate.py
退出码 0 = 全部通过（才允许推送）；非 0 = 有失败项，禁止发布。

校验分两层：
  A. 结构层 —— br- 模板、锚点、链接解析、JSON、去 emoji（全部报告）
  B. 内容层 —— 精选卡四字段 + 建议行动 + 来源、字段/摘要字数下限、links 非空
     （对 ENFORCE_FROM 之后的报告强制；历史报告仅告警不判失败——正文不回改原则）
"""
import json, re, os, glob, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENFORCE_FROM = "2026-07-13"   # 内容层硬校验的起始日期（此前为历史存档）
MIN_FIELD = 30                # 精选卡每个标准字段的最少字数（去标签后）
MIN_BRIEF = 40                # topics.json brief 的最少字数

FIELD_WHAT   = "是什么"
FIELD_VALUE  = "对你的价值"
FIELD_DEPLOY = ("怎么部署", "怎么应对")   # 前缀匹配，允许「怎么部署（分级路由）」等细分
FIELD_PIT    = ("坑与验证", "怎么验证")

OLD_CLASSES = ['class="card"', 'class="field"', 'class="action', 'class="links"',
               'class="ext"', 'noise-card', 'class="review"', 'class="badge',
               'batch-sep', 'prev-link', 'assets/style.css']
EMOJI = ['✅', '🔶', '⚠', '📡', '🎯', '🚫']

fails, warns = [], []
def fail(msg): fails.append(msg)
def warn(msg): warns.append(msg)

def strip_tags(s): return re.sub(r"<[^>]+>", "", s)

def matching_close(s, start, tag):
    depth = 0
    for m in re.finditer(r"<%s\b|</%s>" % (tag, tag), s[start:]):
        depth += -1 if m.group().startswith("</") else 1
        if depth == 0: return start + m.end()
    return len(s)

# ---------- A. 数据层 ----------
data_path = os.path.join(REPO, "docs/data/topics.json")
try:
    D = json.load(open(data_path, encoding="utf-8"))
except Exception as e:
    print("FATAL topics.json 不可解析:", e); sys.exit(1)

for k, v in D.get("categories", {}).items():
    if any(c in v for c in EMOJI) or re.search(r"[\U0001F000-\U0001FAFF]", v):
        fail("分类名含 emoji: %s=%s" % (k, v))

allids = {t["id"] for t in D["topics"]}
for t in D["topics"]:
    tid, date = t["id"], t.get("date", "")
    if not t.get("links"):
        (fail if date >= ENFORCE_FROM else warn)("topic %s links[] 为空（原始信源缺失）" % tid)
    if len(t.get("brief", "")) < MIN_BRIEF:
        (fail if date >= ENFORCE_FROM else warn)("topic %s brief 少于 %d 字" % (tid, MIN_BRIEF))
    u = t.get("url") or ""
    if u.startswith("reports/") and "#" in u and "#topic-" not in u:
        fail("topic %s url 锚点缺 topic- 前缀: %s" % (tid, u))

for h in D.get("hot", []):
    ids = h.get("topicIds", [])
    if not ids: fail("hot %s 无 topicIds" % h.get("tag"))
    for i in ids:
        if i not in allids: fail("hot %s 引用不存在的 topic %s" % (h.get("tag"), i))

for p in D.get("picks", []):
    for i in p.get("topicIds", []):
        if i not in allids: fail("pick 「%s…」引用不存在的 topic %s" % (p.get("title", "?")[:16], i))

# ---------- B. 报告层 ----------
report_ids = {}
for rp in sorted(glob.glob(os.path.join(REPO, "docs/reports/20*.html"))):
    date = os.path.basename(rp)[:-5]
    s = open(rp, encoding="utf-8").read()
    hard = date >= ENFORCE_FROM
    say = fail if hard else warn

    if '<div class="br-app"' not in s: fail("%s 缺 br-app 根节点" % date)
    if "../style.css" not in s: fail("%s 未外链 ../style.css" % date)
    for o in OLD_CLASSES:
        if o in s: fail("%s 残留旧结构 %s" % (date, o))
    for g in EMOJI:
        if g in s: fail("%s 正文含 emoji %s" % (date, g))
    n_table = len(re.findall(r"<table", s))
    if n_table != s.count('br-scroll-x"><table'):
        fail("%s 存在未包裹 br-scroll-x 的表格" % date)
    if re.search(r"<p>\s*</p>", s): fail("%s 有空段落" % date)
    report_ids[date] = set(re.findall(r'id="topic-([^"]+)"', s))

    # 精选卡内容模板（带 id 的 br-report-card；复盘卡无 id，豁免）
    for m in re.finditer(r'<article class="br-report-card" id="topic-([^"]+)">', s):
        cid = m.group(1)
        block = s[m.start():matching_close(s, m.start(), "article")]
        heads = re.findall(r'br-field__h">([^<]+)</h3>', block)
        def has(spec):
            names = (spec,) if isinstance(spec, str) else spec
            return any(any(h.startswith(n) for n in names) for h in heads)
        for spec, label in ((FIELD_WHAT, "是什么"), (FIELD_VALUE, "对你的价值"),
                            (FIELD_DEPLOY, "怎么部署/怎么应对"), (FIELD_PIT, "坑与验证")):
            if not has(spec): say("%s #%s 精选卡缺字段「%s」" % (date, cid, label))
        if "br-act-box" not in block: say("%s #%s 精选卡缺「建议行动」" % (date, cid))
        if not has("来源") and "br-source" not in block: say("%s #%s 精选卡缺「来源」" % (date, cid))
        for fm in re.finditer(r'<div class="br-field"><h3 class="br-field__h">([^<]+)</h3>(.*?)</div>', block, re.S):
            name, body = fm.group(1), strip_tags(fm.group(2)).strip()
            if name.startswith(("来源",)): continue
            if len(body) < MIN_FIELD:
                say("%s #%s 字段「%s」仅 %d 字（<%d，疑似偷薄）" % (date, cid, name, len(body), MIN_FIELD))

# 锚点解析：topics/picks 的站内 url 必须指到真实 id
def resolve(u, who):
    m = re.match(r"reports/(\d{4}-\d{2}-\d{2})\.html(?:#topic-(.+))?$", u or "")
    if not m: return
    date, tid = m.group(1), m.group(2)
    if date not in report_ids: fail("%s url 指向不存在的报告 %s" % (who, date)); return
    if tid and tid not in report_ids[date]:
        fail("%s 锚点 #topic-%s 不在 %s 中" % (who, tid, date))
for t in D["topics"]: resolve(t.get("url"), "topic " + t["id"])
for p in D.get("picks", []): resolve(p.get("url"), "pick " + p.get("title", "?")[:16])

# days 与报告文件一致
file_dates = {os.path.basename(r)[:-5] for r in glob.glob(os.path.join(REPO, "docs/reports/20*.html"))}
day_dates = {d["date"] for d in D.get("days", [])}
for miss in sorted(file_dates - day_dates): fail("报告 %s 缺 days[] 入口" % miss)

# ---------- 首页 ----------
idx = open(os.path.join(REPO, "docs/index.html"), encoding="utf-8").read()
if "topics.json" not in idx: fail("index 未接 topics.json")
if "hashchange" not in idx: fail("index 缺 hash 路由（问题1回归）")
if "t.links" not in idx: fail("index 详情页未渲染原始信源（问题2回归）")

# ---------- 汇总 ----------
for w in warns: print("  ⚠ 告警(历史存档，不判失败):", w)
if fails:
    print("\n== %d 项校验失败，禁止发布 ==" % len(fails))
    for f in fails: print("  ✗", f)
    sys.exit(1)
print("\n== 校验全部通过（告警 %d 项为历史存档）==" % len(warns))
