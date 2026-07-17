#!/usr/bin/env python3
# 将飞机杯商品评价 CSV 解析为虚拟用户压力测试工具的示例 VOC 数据集。
# 输出 ./voc-source.js (window.DEMO_VOC)，按 8 个分群键组织。
# 与 voc-report 的九大标签模块对齐：用户画像/购买动机/购买目的/使用场景/
# 使用阻碍/克服方式/用户忠诚度/产品改进建议/十三种需求。
import csv, sys, json, re, datetime, random

csv.field_size_limit(sys.maxsize)
CAP = 200  # 每分群保留的代表性样本上限（控文件体积，适配 GitHub Contents API 1MB 限制）
SRC = "/Users/fsw/Downloads/飞机杯商品评价数据源_美亚欧亚汇总-3星及以下.csv"
OUT = "/Users/fsw/WorkBuddy/2026-07-15-15-11-41/virtual-user-stress-test/voc-source.js"

SEG_KEYS = ["innovator","price","quality","watcher","pain","kol","critic","competitor"]

def split_tags(s):
    """按逗号/顿号切分，但合并被括号跨断的片段（如「性价比需求（价格合理,物有所值）」）。"""
    if not s: return []
    raw = [t.strip() for t in re.split(r"[,，、]", s) if t.strip()]
    merged, buf, depth = [], "", 0
    for t in raw:
        depth += t.count("（") + t.count("(") - t.count("）") - t.count(")")
        buf = (buf + "，" + t) if buf else t
        if depth <= 0:
            merged.append(buf); buf = ""
    if buf: merged.append(buf)
    return [m for m in merged if m not in ("无法判定", "无", "不确定", "")]

def expand_tag(t):
    """返回 [清理后的主标签, *括号内细粒度词]，供引擎做关键词匹配。"""
    out = [strip_paren(t)]
    m = re.search(r"[（(](.*)[)）]", t)
    if m:
        for inner in re.split(r"[,，、]", m.group(1)):
            inner = inner.strip()
            if inner and inner not in ("无法判定", "无", ""):
                out.append(inner)
    return out

def tag_array(field):
    res = []
    for t in split_tags(field):
        for x in expand_tag(t):
            if x not in res:
                res.append(x)
    return res

def strip_paren(s):
    return re.sub(r"[（(].*?[)）]", "", s).strip()

def norm_sentiment(emo):
    e = emo or ""
    if ("不满" in e) or ("负" in e): return "负"
    if ("满意" in e) or ("正" in e): return "正"
    return "中"

def cap(s, n):
    if not s: return ""
    s = s.replace("\n", " ").replace("\r", " ").strip()
    return s if len(s) <= n else s[:n] + "…"

# 参考价提取：覆盖中英文货币表达
PRICE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:元|块|刀|美金|美元|欧元|块钱|RMB|￥|eur|euro|usd|dollar|\$)", re.I)

def extract_price(*texts):
    for t in texts:
        if not t: continue
        m = PRICE_RE.search(t)
        if m:
            return float(m.group(1))
    return None

def compute_intensity(voice, star):
    try: star_n = int(star)
    except (ValueError, TypeError): star_n = 3
    excl = voice.count("!") + voice.count("！") + voice.count("?") + voice.count("？")
    length_factor = min(1.0, len(voice) / 200.0)
    intensity = 0.25 + (0.30 if star_n <= 2 else 0.0) + min(0.20, excl * 0.04) + length_factor * 0.30
    return round(min(1.0, max(0.0, intensity)), 2)

def classify(row):
    probs = split_tags(row.get("产品问题标签", ""))
    needs = split_tags(row.get("需求维度标签库", ""))
    emo_raw = row.get("情绪标签库", "")
    emo = norm_sentiment(emo_raw)
    has_video = (row.get("是否有视频", "") or "").strip().upper() == "Y"
    try: up = int(row.get("赞同数", "") or 0)
    except ValueError: up = 0
    red = bool((row.get("红人计划链接", "") or "").strip())
    alltags = probs + needs

    if any(("竞品" in t) or (("兼容" in t) and ("不兼容" not in t)) or ("迁移成本" in t) for t in alltags):
        return "competitor"
    if red or (has_video and up >= 10):
        return "kol"
    if any(("性价比" in t) or ("价格" in t) for t in alltags):
        return "price"
    if any(("安全" in t) or ("材质" in t) or ("品质" in t) or ("质量" in t) for t in alltags):
        return "quality"
    if emo == "负" and (has_video or up >= 5):
        return "critic"
    if emo == "中":
        return "watcher"
    if emo == "负":
        return "pain"
    if emo == "正":
        return "innovator"
    return "watcher"

def main():
    pools = {k: [] for k in SEG_KEYS}
    counts = {k: 0 for k in SEG_KEYS}
    total = 0
    asin_set = set()
    country_c = {}
    cat_c = {}
    price_found = 0
    with open(SRC, encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        for row in r:
            total += 1
            asin_set.add(row.get("ASIN", ""))
            c = (row.get("所属国家", "") or "").strip()
            if c: country_c[c] = country_c.get(c, 0) + 1
            cn = cap(row.get("内容评价-翻译", ""), 160)
            en = cap(row.get("内容", ""), 190)
            voice = cn if cn else en
            if (not voice) or len(voice) < 6 or voice in ("无法判定",):
                continue
            seg = classify(row)
            counts[seg] += 1

            barriers = tag_array(row.get("产品问题标签", ""))
            needs = tag_array(row.get("需求维度标签库", ""))
            profile = tag_array(row.get("用户属性", ""))
            scenarios = tag_array(row.get("使用场景标签", ""))
            try: up = int(row.get("赞同数", "") or 0)
            except ValueError: up = 0
            red = bool((row.get("红人计划链接", "") or "").strip())
            star = (row.get("星级", "") or "").strip()
            refPrice = extract_price(cn, en)
            if refPrice: price_found += 1
            # 标签体系覆盖统计（很多用户没提到有价值内容，打不上很正常）
            for t in barriers + needs: cat_c[t] = cat_c.get(t, 0) + 1

            entry = {
                "voice": voice,
                "voiceEN": en,
                "sentiment": norm_sentiment(row.get("情绪标签库", "")),
                "star": star,
                "country": c,
                "helpful": up,
                "isKOL": red,
                "hasVideo": (row.get("是否有视频", "") or "").strip().upper() == "Y",
                # ---- 标签体系对齐字段 ----
                "barriers": barriers,      # 使用阻碍 / 产品问题
                "needs": needs,            # 产品改进建议 / 需求维度
                "profile": profile,        # 用户画像
                "scenarios": scenarios,    # 使用场景
                # ---- 预计算索引 ----
                "refPrice": refPrice,      # 参考价（从原话提取，可能为空）
                "intensity": compute_intensity(voice, star),  # 情绪/表达强度 0~1
                "pain_words": barriers + needs,  # 关键词并集，供相关性检索
            }
            pools[seg].append(entry)

    meta = {
        "name": "飞机杯·淋浴支架 真实 VOC 示例",
        "source": "美亚欧亚汇总 · 3星及以下（差评/中评源头）",
        "total": total,
        "asinCount": len(asin_set),
        "priceFound": price_found,
        "generatedAt": datetime.date.today().isoformat(),
        "countries": dict(sorted(country_c.items(), key=lambda x: -x[1])[:8]),
        "segmentCounts": counts,
        "tagCoverage": dict(sorted(cat_c.items(), key=lambda x: -x[1])[:12]),
        "mapping": "按 情绪/产品问题/需求维度/用户属性/使用场景/红人/视频/赞同数 映射到 8 分群；barriers/needs/profile/scenarios 对齐 voc-report 九大标签模块",
        "note": "很多人未提及有价值的标签内容，打不上很正常；引擎仅使用有标签/有价格的样本做相关性计算",
    }

    rng = random.Random(20260717)
    for k in pools:
        if len(pools[k]) > CAP:
            rng.shuffle(pools[k])
            pools[k] = pools[k][:CAP]

    payload = {"meta": meta, "segments": pools}
    js = "// 飞机杯商品真实 VOC 示例数据集（由 CSV 解析生成，仅作演示）\n"
    js += "window.DEMO_VOC = " + json.dumps(payload, ensure_ascii=False, indent=1) + ";\n"
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(js)

    print("total rows:", total)
    print("ASINs:", len(asin_set))
    print("price extracted:", price_found)
    print("segment counts:", json.dumps(counts, ensure_ascii=False))
    print("top tags:", json.dumps(dict(sorted(cat_c.items(), key=lambda x:-x[1])[:12]), ensure_ascii=False))
    print("output bytes:", len(js.encode("utf-8")))

if __name__ == "__main__":
    main()
