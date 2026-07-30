#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宇航员创作工作台 - 每日抓取脚本（v2 - 稳定版）
================================================================
数据源升级：
  - 主数据源：DailyHotApi (https://api-hot.imsyy.top) - 40+ 平台聚合
  - 备用数据源：原始平台接口 + vvhan API
  - 微信专辑：RSSHub

功能：
  Part A. 爆款热点抓取 + AI 改写 → data/hot_content.json
  Part B. 投资理财数据 → data/finance.json
  Part C. 自动 git commit + push（GitHub Actions 环境下）

使用方法：
  python hot_scraper.py                    # 抓取全部
  python hot_scraper.py --only hot         # 只抓热点
  python hot_scraper.py --only finance     # 只抓财经
  python hot_scraper.py --commit           # 抓取后自动 commit + push
"""

import json
import os
import re
import sys
import argparse
import subprocess
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

# ============== 配置 ==============
# DailyHotApi 官方 demo（GitHub Actions 海外服务器可访问）
# 备选：可自部署 Vercel 版本 https://your-dailyhot.vercel.app
DAILYHOT_API = os.getenv("DAILYHOT_API", "https://api-hot.imsyy.top").rstrip("/")

# 要抓取的平台列表
HOT_PLATFORMS = ["douyin", "weibo", "bilibili", "zhihu", "toutiao", "xiaohongshu"]

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "") or os.getenv("GH_TOKEN", "")
GIST_ID = os.getenv("GIST_ID", "")
GIST_FILENAME_HOT = "hot_content.json"
GIST_FILENAME_FIN = "finance.json"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

WX_RSS_URLS = [u.strip() for u in os.getenv("WX_RSS_URLS", "").split(",") if u.strip()]
TRACK_NAME = "彩妆好物 / 护肤好物"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_HOT = os.path.join(BASE_DIR, "data", "hot_content.json")
OUTPUT_FIN = os.path.join(BASE_DIR, "data", "finance.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

DEFAULT_FUND_CODES = ["110011", "161725", "005827", "270042", "320007"]
FUND_CODES = [c.strip() for c in os.getenv("FUNDS", "").split(",") if c.strip()] or DEFAULT_FUND_CODES


# ============================================================
# Part A: 爆款热点抓取（DailyHotApi 为主）
# ============================================================
def fetch_dailyhot(platform: str) -> list:
    """通过 DailyHotApi 抓取单个平台热榜"""
    try:
        url = f"{DAILYHOT_API}/{platform}"
        res = requests.get(url, headers=HEADERS, timeout=15)
        if res.status_code == 200:
            data = res.json()
            if data.get("code") == 200 and data.get("data"):
                platform_names = {
                    "douyin": "抖音热榜", "weibo": "微博热搜", "bilibili": "B站热门",
                    "zhihu": "知乎热榜", "toutiao": "今日头条", "xiaohongshu": "小红书热榜"
                }
                items = []
                for it in data["data"][:15]:
                    items.append({
                        "title": it.get("title", ""),
                        "hot": it.get("hot", "") or it.get("mobileUrl", ""),
                        "url": it.get("url", ""),
                        "source": platform_names.get(platform, platform)
                    })
                return items
    except Exception as e:
        print(f"  [{platform} DailyHotApi] {e}", file=sys.stderr)
    return []


def fetch_bilibili_direct() -> list:
    """B站直连接口（备用）"""
    try:
        res = requests.get("https://api.bilibili.com/x/web-interface/ranking/v2?rid=0&type=all",
                          headers=HEADERS, timeout=10)
        if res.status_code == 200:
            data = res.json()
            return [
                {"title": it.get("title", ""), "hot": it.get("stat", {}).get("view", 0), "source": "B站热门"}
                for it in (data.get("data", {}).get("list") or [])[:15]
            ]
    except Exception as e:
        print(f"  [B站直连] {e}", file=sys.stderr)
    return []


def fetch_weibo_direct() -> list:
    """微博热搜直连（备用）"""
    try:
        res = requests.get("https://weibo.com/ajax/side/hotSearch", headers=HEADERS, timeout=10)
        if res.status_code == 200:
            data = res.json()
            items = []
            for it in (data.get("data", {}).get("realtime") or [])[:15]:
                items.append({
                    "title": it.get("note", "") or it.get("word", ""),
                    "hot": it.get("num", 0),
                    "source": "微博热搜"
                })
            return items
    except Exception as e:
        print(f"  [微博直连] {e}", file=sys.stderr)
    return []


def fetch_douyin_direct() -> list:
    """抖音热榜直连（备用）"""
    try:
        pc_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Referer": "https://www.douyin.com/"
        }
        res = requests.get("https://www.douyin.com/aweme/v1/web/hotsearch/list/",
                          headers=pc_headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            return [
                {"title": it.get("word", ""), "hot": it.get("hot_value", 0), "source": "抖音热榜"}
                for it in (data.get("data", {}).get("word_list") or [])[:15]
            ]
    except Exception as e:
        print(f"  [抖音直连] {e}", file=sys.stderr)
    return []


def fetch_zhihu_direct() -> list:
    """知乎热榜直连（备用）"""
    try:
        res = requests.get("https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total?limit=15",
                          headers={**HEADERS, "Referer": "https://www.zhihu.com/hot"}, timeout=10)
        if res.status_code == 200:
            data = res.json()
            return [
                {"title": it.get("target", {}).get("title", ""),
                 "hot": it.get("detail_text", ""),
                 "source": "知乎热榜"}
                for it in (data.get("data") or [])[:15]
            ]
    except Exception as e:
        print(f"  [知乎直连] {e}", file=sys.stderr)
    return []


def fetch_toutiao_direct() -> list:
    """今日头条热榜直连（备用）"""
    try:
        res = requests.get("https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc",
                          headers=HEADERS, timeout=10)
        if res.status_code == 200:
            data = res.json()
            return [
                {"title": it.get("Title", ""), "hot": it.get("HotValue", ""), "source": "今日头条"}
                for it in (data.get("data") or [])[:15]
            ]
    except Exception as e:
        print(f"  [头条直连] {e}", file=sys.stderr)
    return []


def fetch_wechat_mp() -> list:
    """微信公众号专辑 - 通过 RSSHub"""
    items = []
    for rss_url in WX_RSS_URLS:
        try:
            res = requests.get(rss_url, headers=HEADERS, timeout=10)
            if res.status_code != 200:
                continue
            xml = res.text
            item_blocks = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
            for block in item_blocks[:10]:
                title_m = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>|<title>(.*?)</title>", block)
                desc_m = re.search(r"<description><!\[CDATA\[(.*?)\]\]></description>|<description>(.*?)</description>", block, re.DOTALL)
                pub_m = re.search(r"<pubDate>(.*?)</pubDate>", block)
                title = (title_m.group(1) or title_m.group(2)).strip() if title_m else ""
                if not title:
                    continue
                summary = ""
                if desc_m:
                    raw = (desc_m.group(1) or desc_m.group(2) or "").strip()
                    summary = re.sub(r"<[^>]+>", "", raw)[:200]
                pub_time = pub_m.group(1).strip() if pub_m else ""
                items.append({
                    "title": title, "summary": summary,
                    "source": "微信专辑", "time": pub_time
                })
        except Exception as e:
            print(f"  [微信 {rss_url}] {e}", file=sys.stderr)
    return items


def fetch_all_hot() -> list:
    """并行抓取所有平台热榜，主源 + 备用源同时跑"""
    print("[热点] 正在并行抓取多平台热榜...")
    all_items = []

    # 同时启动主源（DailyHotApi）和备用源（直连接口）
    all_tasks = {}
    for p in HOT_PLATFORMS:
        all_tasks[("dailyhot", p)] = ("dailyhot", p)
    all_tasks[("direct", "bilibili")] = ("direct", "bilibili")
    all_tasks[("direct", "weibo")] = ("direct", "weibo")
    all_tasks[("direct", "douyin")] = ("direct", "douyin")
    all_tasks[("direct", "zhihu")] = ("direct", "zhihu")
    all_tasks[("direct", "toutiao")] = ("direct", "toutiao")

    with ThreadPoolExecutor(max_workers=11) as ex:
        futures = {}
        for key, val in all_tasks.items():
            src_type, platform = val
            if src_type == "dailyhot":
                futures[ex.submit(fetch_dailyhot, platform)] = f"DailyHotApi/{platform}"
            else:
                direct_fns = {
                    "bilibili": fetch_bilibili_direct,
                    "weibo": fetch_weibo_direct,
                    "douyin": fetch_douyin_direct,
                    "zhihu": fetch_zhihu_direct,
                    "toutiao": fetch_toutiao_direct,
                }
                futures[ex.submit(direct_fns[platform])] = f"Direct/{platform}"

        for f in as_completed(futures):
            label = futures[f]
            try:
                items = f.result()
                if items:
                    print(f"  ✓ {label}: {len(items)} 条")
                    all_items.extend(items)
                else:
                    print(f"  · {label}: 0 条")
            except Exception as e:
                print(f"  ✗ {label}: {e}", file=sys.stderr)

    # 微信专辑
    if WX_RSS_URLS:
        print("  [微信专辑] 抓取中...")
        wx_items = fetch_wechat_mp()
        print(f"  ✓ 微信专辑: {len(wx_items)} 条")
        all_items.extend(wx_items)

    # 去重（按标题）
    seen, unique = set(), []
    for it in all_items:
        t = it.get("title", "").strip()
        if t and t not in seen:
            seen.add(t)
            unique.append(it)

    platforms = list(set(it["source"] for it in unique))
    print(f"\n  共抓取 {len(unique)} 条原始热榜数据（来自 {len(platforms)} 个平台：{', '.join(platforms)}）")
    return unique[:80]


# ============== AI 改写 ==============
def rewrite_with_openai(hot_items: list) -> dict:
    if not OPENAI_API_KEY:
        return None
    try:
        items_text = "\n".join(f"- [{it['source']}] {it['title']}" for it in hot_items[:40])
        prompt = f"""你是彩妆好物 / 护肤好物分享赛道的爆款内容策划师。
请基于以下今日全网热榜，生成贴合博主赛道的爆款内容建议。

【今日热榜】
{items_text}

【要求】
1. 输出严格 JSON，不要任何额外解释
2. ideas: 10 条，每条 {{title, tags:[2-3个标签], angle(选题角度/钩子,一句话)}}
3. recreate: 10 条，每条 {{source, title(改编后标题), angle(切入角度), tags:[2-3个标签]}}
4. 全部要能挂小黄车卖货，标题要有爆款感（前3秒钩子/痛点/反差）
5. 围绕：彩妆教程、产品测评、好物推荐、护肤成分、妆容风格、季节护肤、平价彩妆、明星同款等"""
        res = requests.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": OPENAI_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.9,
                "response_format": {"type": "json_object"}
            },
            timeout=60
        )
        if res.status_code == 200:
            return json.loads(res.json()["choices"][0]["message"]["content"])
    except Exception as e:
        print(f"[OpenAI] {e}", file=sys.stderr)
    return None


def rewrite_with_rules(hot_items: list) -> dict:
    """本地规则改写 - 基于真实热榜做赛道化改编"""
    import random
    print("[热点] 使用本地规则改写（未配置 OPENAI_API_KEY）...")

    # 通用选题模板（不依赖热榜，作为补充）
    static_ideas = [
        ("{product}用了3年回购8次！真心建议所有姐妹冲", ["#回购清单", "#平价彩妆"], "长期回购型好物推荐"),
        ("黄黑皮逆袭！这个{product}让我白到发光", ["#黄黑皮", "#提亮"], "肤色痛点 + 解决方案"),
        ("被闺蜜追着问的口红色号！{brand}也太懂女生了吧", ["#口红试色", "#爆款色号"], "闺蜜种草 + 试色展示"),
        ("早八人通勤妆容｜5分钟搞定同事都问链接", ["#早八妆容", "#通勤妆"], "效率场景 + 速成感"),
        ("烂脸救星！烂脸期{product}急救护肤流程", ["#烂脸急救", "#敏感肌护肤"], "痛点场景 + 急救方案"),
    ]
    products = ["粉底液", "口红", "眼影盘", "面膜", "精华", "面霜", "化妆水", "卸妆膏", "防晒霜", "眉笔"]
    brands = ["花西子", "完美日记", "橘朵", "毛戈平", "酵色", "INTO YOU", "Colorkey", "玛丽黛佳", "卡姿兰"]
    hooks = ["实测避雷", "保姆级教程", "姐妹们冲", "千万别买错", "回购8次", "亲测好用", "性价比之王"]

    def short_title(t, max_len=15):
        """截断长标题"""
        t = re.sub(r"【.*?】", "", t)  # 去掉【】标记
        t = re.sub(r"[|｜].*", "", t)  # 去掉 | 后面的
        t = t.strip()
        return t[:max_len] + "…" if len(t) > max_len else t

    ideas = []
    # 前 5 条基于真实热榜改编（标题精简化）
    for it in hot_items[:5]:
        original = it.get("title", "")
        if not original:
            continue
        short = short_title(original)
        brand = random.choice(brands)
        product = random.choice(products)
        hook = random.choice(hooks)
        ideas.append({
            "title": f"借势「{short}」｜{brand}{product}{hook}",
            "tags": ["#借势热点", "#好物测评"],
            "angle": f"借势热榜话题，挂{brand}{product}小黄车"
        })
    # 后 5 条用静态模板
    for title, tags, angle in static_ideas:
        t = title.replace("{product}", random.choice(products)).replace("{brand}", random.choice(brands))
        ideas.append({"title": t, "tags": tags, "angle": angle})

    # 二创角度：从热榜里挑 10 条（标题精简化）
    recreate = []
    for it in hot_items[:10]:
        original = it.get("title", "")
        src = it.get("source", "全网热榜")
        if not original:
            continue
        short = short_title(original)
        if any(k in original for k in ["妆", "美", "护肤", "面膜", "口红", "眼影", "粉底", "穿搭", "时尚"]):
            angle = f"借势「{short}」热度，做同款妆容/护肤流程拆解，挂同类爆品小黄车"
            title = f"「{short}」同款妆容拆解｜{random.choice(brands)}{random.choice(products)}实测"
            tags = ["#借势热点", "#同款"]
        else:
            scene = random.choice(['明星同款妆容', '通勤妆拆解', '氛围感妆容'])
            angle = f"把「{short}」话题嫁接到美妆场景：{scene}，自然挂小黄车"
            title = f"「{short}」×美妆｜{random.choice(['这3支口红必入', '5分钟打造同款氛围感', '偷师明星化妆师'])}"
            tags = ["#跨界借势", "#氛围感"]
        recreate.append({"source": src, "original": short, "title": title, "angle": angle, "tags": tags})

    return {"ideas": ideas, "recreate": recreate}


# ============================================================
# Part B: 投资理财数据抓取
# ============================================================
def fetch_indexes() -> list:
    """大盘指数 - 新浪财经"""
    print("[财经] 抓取大盘指数...")
    codes = [("sh000001", "上证指数"), ("sz399001", "深证成指"), ("sz399006", "创业板指")]
    indexes = []
    for code, name in codes:
        try:
            url = f"https://hq.sinajs.cn/list=s_{code}"
            headers = {"Referer": "https://finance.sina.com.cn", **HEADERS}
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                m = re.search(r'"([^"]+)"', res.text)
                if m:
                    parts = m.group(1).split(",")
                    if len(parts) >= 4:
                        indexes.append({
                            "name": parts[0] or name,
                            "value": parts[1],
                            "change": float(parts[3]) if parts[3] else 0
                        })
        except Exception as e:
            print(f"  [指数 {code}] {e}", file=sys.stderr)
    return indexes


def fetch_fund_nav(code: str) -> dict:
    """单只基金净值 - 天天基金"""
    try:
        url = f"https://fundgz.1234567.com.cn/js/{code}.js"
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            m = re.search(r'jsonpgz\((.+?)\);', res.text)
            if m:
                d = json.loads(m.group(1))
                return {
                    "code": d.get("fundcode", code),
                    "name": d.get("name", ""),
                    "nav": d.get("gsz") or d.get("dwjz", "--"),
                    "change": float(d.get("gszzl", 0)) if d.get("gszzl") else 0,
                    "time": d.get("gztime", "")
                }
    except Exception as e:
        print(f"  [基金 {code}] {e}", file=sys.stderr)
    return {"code": code, "name": "", "nav": "--", "change": 0, "time": ""}


def fetch_all_funds() -> list:
    print(f"[财经] 抓取 {len(FUND_CODES)} 只自选基金净值...")
    results = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(fetch_fund_nav, c): c for c in FUND_CODES}
        for f in as_completed(futures):
            try:
                results.append(f.result())
            except Exception as e:
                print(f"  基金失败: {e}", file=sys.stderr)
    return results


def fetch_finance_news() -> list:
    """财经快讯 - RSSHub"""
    print("[财经] 抓取财经快讯...")
    news = []
    rss_urls = [
        ("https://rsshub.app/cls/telegraph", "财联社"),
        ("https://rsshub.app/finance/sina/finance", "新浪财经"),
    ]
    for rss_url, source in rss_urls:
        try:
            res = requests.get(rss_url, headers=HEADERS, timeout=10)
            if res.status_code != 200:
                continue
            xml = res.text
            item_blocks = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
            for block in item_blocks[:10]:
                title_m = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>|<title>(.*?)</title>", block)
                desc_m = re.search(r"<description><!\[CDATA\[(.*?)\]\]></description>|<description>(.*?)</description>", block, re.DOTALL)
                pub_m = re.search(r"<pubDate>(.*?)</pubDate>", block)
                title = (title_m.group(1) or title_m.group(2)).strip() if title_m else ""
                if not title:
                    continue
                summary = ""
                if desc_m:
                    raw = (desc_m.group(1) or desc_m.group(2) or "").strip()
                    summary = re.sub(r"<[^>]+>", "", raw)[:200]
                news.append({
                    "title": title, "summary": summary, "source": source,
                    "time": pub_m.group(1).strip() if pub_m else ""
                })
        except Exception as e:
            print(f"  [{source}] {e}", file=sys.stderr)
        if news:
            break
    return news[:15]


def build_finance_data() -> dict:
    return {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "indexes": fetch_indexes(),
        "funds": fetch_all_funds(),
        "news": fetch_finance_news()
    }


# ============== Gist 推送 ==============
def push_to_gist(content: str, filename: str) -> bool:
    if not GITHUB_TOKEN or not GIST_ID:
        return False
    url = f"https://api.github.com/gists/{GIST_ID}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Content-Type": "application/json"}
    payload = {"files": {filename: {"content": content}}}
    try:
        res = requests.patch(url, headers=headers, json=payload, timeout=15)
        if res.status_code == 200:
            print(f"[Gist] ✓ {filename} 已推送")
            return True
        print(f"[Gist] ✗ {res.status_code}", file=sys.stderr)
    except Exception as e:
        print(f"[Gist] {e}", file=sys.stderr)
    return False


# ============== Git 提交（GitHub Actions 环境）==============
def git_commit_push():
    """在 GitHub Actions 环境中自动 commit + push 更新的 JSON 文件"""
    print("\n[Git] 准备提交数据更新...")
    try:
        # 配置 git
        subprocess.run(["git", "config", "user.email", "actions@github.com"], check=True)
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)

        # 添加数据文件
        subprocess.run(["git", "add", "data/hot_content.json", "data/finance.json"], check=True)

        # 检查是否有变更
        result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True)
        if not result.stdout.strip():
            print("[Git] 无数据变更，跳过提交")
            return False

        # 提交
        commit_msg = f"📡 自动更新热榜数据 - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        subprocess.run(["git", "commit", "-m", commit_msg], check=True)

        # 推送
        subprocess.run(["git", "push"], check=True)
        print(f"[Git] ✓ 已提交并推送：{commit_msg}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[Git] ✗ 提交失败：{e}", file=sys.stderr)
        return False


# ============== Main ==============
def run_hot():
    print("\n" + "=" * 60)
    print("🚀 Part A: 爆款热点抓取")
    print("=" * 60)
    hot_items = fetch_all_hot()
    rewritten = rewrite_with_openai(hot_items) or rewrite_with_rules(hot_items)
    output = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "track": TRACK_NAME,
        "source_count": len(hot_items),
        "platforms": list(set(it["source"] for it in hot_items)),
        "raw_hot": hot_items[:40],
        "ideas": rewritten.get("ideas", [])[:10],
        "recreate": rewritten.get("recreate", [])[:10]
    }
    os.makedirs(os.path.dirname(OUTPUT_HOT), exist_ok=True)
    with open(OUTPUT_HOT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n✓ 本地: {OUTPUT_HOT}")
    print(f"  选题灵感: {len(output['ideas'])} 条 / 二创角度: {len(output['recreate'])} 条")
    push_to_gist(json.dumps(output, ensure_ascii=False, indent=2), GIST_FILENAME_HOT)


def run_finance():
    print("\n" + "=" * 60)
    print("💰 Part B: 投资理财数据抓取")
    print("=" * 60)
    fin_data = build_finance_data()
    os.makedirs(os.path.dirname(OUTPUT_FIN), exist_ok=True)
    with open(OUTPUT_FIN, "w", encoding="utf-8") as f:
        json.dump(fin_data, f, ensure_ascii=False, indent=2)
    print(f"\n✓ 本地: {OUTPUT_FIN}")
    print(f"  指数 {len(fin_data['indexes'])} 个 / 基金 {len(fin_data['funds'])} 只 / 快讯 {len(fin_data['news'])} 条")
    push_to_gist(json.dumps(fin_data, ensure_ascii=False, indent=2), GIST_FILENAME_FIN)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["hot", "finance"], help="只跑某一部分")
    parser.add_argument("--commit", action="store_true", help="抓取后自动 git commit + push")
    args = parser.parse_args()

    print(f"\n🚀 宇航员创作工作台 · 每日抓取 v2")
    print(f"   时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   数据源：DailyHotApi ({DAILYHOT_API})")

    if not args.only or args.only == "hot":
        run_hot()
    if not args.only or args.only == "finance":
        run_finance()

    if args.commit:
        git_commit_push()

    print("\n" + "=" * 60)
    print("✅ 完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()