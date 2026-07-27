#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宇航员创作工作台 - 每日抓取脚本（升级版）
================================================================
功能：
  Part A. 爆款热点抓取
    1. 并行抓取抖音 / 小红书 / B 站 / 微博 四大平台热榜
    2. 抓取指定微信公众号专辑文章（RSSHub）
    3. AI 改写成贴合"彩妆好物 / 护肤好物"赛道的 10 条选题 + 10 条二创
    4. 推送到公开 GitHub Gist
    5. 输出 data/hot_content.json 供网页直接读取

  Part B. 投资理财数据抓取
    1. 抓取大盘指数（上证/深证/创业板）
    2. 抓取自选基金净值（天天基金接口）
    3. 抓取财经快讯（财联社/新浪财经 RSS）
    4. 输出 data/finance.json 供网页读取

使用方法：
  pip install requests
  export GITHUB_TOKEN=ghp_xxx
  export GIST_ID=xxxxxxxxxxxx
  export OPENAI_API_KEY=sk-xxx           # 可选
  export WX_RSS_URLS="https://rsshub.app/wechat/mp/账号1,..."  # 可选
  python hot_scraper.py

  # 单独跑某一部分
  python hot_scraper.py --only hot       # 只抓爆款热点
  python hot_scraper.py --only finance   # 只抓财经数据
"""

import json
import os
import re
import sys
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

# ============== 配置 ==============
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GIST_ID = os.getenv("GIST_ID", "")
GIST_FILENAME_HOT = "hot_content.json"
GIST_FILENAME_FIN = "finance.json"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

WX_RSS_URLS = [u.strip() for u in os.getenv("WX_RSS_URLS", "").split(",") if u.strip()]

TRACK_NAME = "彩妆好物 / 护肤好物"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_HOT = os.path.join(BASE_DIR, "data", "hot_content.json")
OUTPUT_FIN = os.path.join(BASE_DIR, "data", "finance.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
}

# 默认自选基金（可被环境变量 FUNDS=代码1,代码2 覆盖）
DEFAULT_FUND_CODES = ["110011", "161725", "005827", "270042", "320007"]
FUND_CODES = [c.strip() for c in os.getenv("FUNDS", "").split(",") if c.strip()] or DEFAULT_FUND_CODES


# ============================================================
# Part A: 爆款热点抓取
# ============================================================
def fetch_douyin_hot() -> list:
    url = "https://www.douyin.com/aweme/v1/web/hotsearch/list/"
    try:
        pc_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Referer": "https://www.douyin.com/"
        }
        res = requests.get(url, headers=pc_headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            return [
                {"title": it.get("word", ""), "hot": it.get("hot_value", 0), "source": "抖音热榜"}
                for it in (data.get("data", {}).get("word_list") or [])[:15]
            ]
    except Exception as e:
        print(f"[抖音] {e}", file=sys.stderr)
    return fetch_backup("douyin")


def fetch_backup(platform: str) -> list:
    """第三方备用接口"""
    urls = {
        "douyin": "https://api.vvhan.com/api/hotlist/douyin",
        "xhs": "https://api.vvhan.com/api/hotlist/xiaohongshu",
        "bili": "https://api.vvhan.com/api/hotlist/bilibili",
        "weibo": "https://api.vvhan.com/api/hotlist/wbHot",
    }
    name_map = {"douyin": "抖音热榜", "xhs": "小红书热榜", "bili": "B站热门", "weibo": "微博热搜"}
    try:
        res = requests.get(urls.get(platform, ""), timeout=10)
        if res.status_code == 200:
            data = res.json()
            return [
                {"title": it.get("title", ""), "hot": it.get("hot", ""), "source": name_map.get(platform, "")}
                for it in (data.get("data") or [])[:15]
            ]
    except Exception as e:
        print(f"[{platform} backup] {e}", file=sys.stderr)
    return []


def fetch_xiaohongshu_hot() -> list:
    return fetch_backup("xhs")


def fetch_bilibili_hot() -> list:
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
        print(f"[B站] {e}", file=sys.stderr)
    return fetch_backup("bili")


def fetch_weibo_hot() -> list:
    return fetch_backup("weibo")


def fetch_wechat_mp() -> list:
    """微信公众号专辑 - 通过 RSSHub，解析 RSS XML 提取标题和摘要"""
    items = []
    for rss_url in WX_RSS_URLS:
        try:
            res = requests.get(rss_url, headers=HEADERS, timeout=10)
            if res.status_code != 200:
                continue
            xml = res.text
            # 提取 item 块
            item_blocks = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
            for block in item_blocks[:10]:
                title_m = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>|<title>(.*?)</title>", block)
                desc_m = re.search(r"<description><!\[CDATA\[(.*?)\]\]></description>|<description>(.*?)</description>", block, re.DOTALL)
                pub_m = re.search(r"<pubDate>(.*?)</pubDate>", block)
                title = (title_m.group(1) or title_m.group(2)).strip() if title_m else ""
                if not title:
                    continue
                # 清理 HTML 标签
                summary = ""
                if desc_m:
                    raw = (desc_m.group(1) or desc_m.group(2) or "").strip()
                    summary = re.sub(r"<[^>]+>", "", raw)[:200]
                pub_time = pub_m.group(1).strip() if pub_m else ""
                items.append({
                    "title": title,
                    "summary": summary,
                    "source": "微信专辑",
                    "time": pub_time
                })
        except Exception as e:
            print(f"[微信 {rss_url}] {e}", file=sys.stderr)
    return items


def fetch_all_hot() -> list:
    print("[热点] 正在并行抓取多平台热榜...")
    tasks = {
        "douyin": fetch_douyin_hot,
        "xhs": fetch_xiaohongshu_hot,
        "bili": fetch_bilibili_hot,
        "weibo": fetch_weibo_hot,
        "wx": fetch_wechat_mp,
    }
    all_items = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(fn): name for name, fn in tasks.items()}
        for f in as_completed(futures):
            name = futures[f]
            try:
                items = f.result()
                print(f"  ✓ {name}: {len(items)} 条")
                all_items.extend(items)
            except Exception as e:
                print(f"  ✗ {name}: {e}", file=sys.stderr)
    # 去重
    seen, unique = set(), []
    for it in all_items:
        t = it.get("title", "").strip()
        if t and t not in seen:
            seen.add(t)
            unique.append(it)
    return unique[:60]


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
                "model": "gpt-4o-mini",
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
    """本地规则改写"""
    import random
    print("[热点] 使用本地规则改写（未配置 OPENAI_API_KEY）...")
    idea_templates = [
        ("{product}用了3年回购8次！真心建议所有姐妹冲", ["#回购清单", "#平价彩妆"], "长期回购型好物推荐"),
        ("黄黑皮逆袭！这个{product}让我白到发光", ["#黄黑皮", "#提亮"], "肤色痛点 + 解决方案"),
        ("被闺蜜追着问的口红色号！{brand}也太懂女生了吧", ["#口红试色", "#爆款色号"], "闺蜜种草 + 试色展示"),
        ("早八人通勤妆容｜5分钟搞定同事都问链接", ["#早八妆容", "#通勤妆"], "效率场景 + 速成感"),
        ("烂脸救星！烂脸期{product}急救护肤流程", ["#烂脸急救", "#敏感肌护肤"], "痛点场景 + 急救方案"),
        ("油皮亲妈！夏天不脱妆的{product}测评", ["#油皮底妆", "#夏日底妆"], "肤质痛点 + 测评"),
        ("学生党必入｜{product}平替大牌省下一个亿", ["#学生党", "#平替"], "价格反差 + 平价好物"),
        ("明星化妆师偷偷用的{product}！同款get", ["#明星同款", "#化妆师推荐"], "权威背书 + 明星效应"),
        ("25+熬夜肌自救｜抗老精华红黑榜", ["#抗老精华", "#熬夜肌"], "年龄焦虑 + 测评对比"),
        ("约会妆氛围感拿捏！斩男色口红榜单", ["#约会妆", "#斩男色"], "场景需求 + 榜单推荐"),
    ]
    products = ["粉底液", "口红", "眼影盘", "面膜", "精华", "面霜", "化妆水", "卸妆膏", "防晒霜", "眉笔"]
    brands = ["花西子", "完美日记", "橘朵", "毛戈平", "酵色", "INTO YOU", "Colorkey", "玛丽黛佳", "卡姿兰"]
    ideas = []
    for title, tags, angle in idea_templates:
        t = title.replace("{product}", random.choice(products)).replace("{brand}", random.choice(brands))
        ideas.append({"title": t, "tags": tags, "angle": angle})

    recreate = []
    for it in hot_items[:10]:
        original = it.get("title", "")
        src = it.get("source", "全网热榜")
        if not original:
            continue
        if any(k in original for k in ["妆", "美", "护肤", "面膜", "口红", "眼影", "粉底"]):
            angle = f"借势「{original}」热度，做同款妆容/护肤流程拆解，挂同类爆品小黄车"
            title = f"{original}｜{random.choice(brands)}{random.choice(products)}实测"
            tags = ["#借势热点", "#同款"]
        else:
            angle = f"把「{original}」话题嫁接到美妆场景：{random.choice(['明星同款妆容', '通勤妆拆解', '氛围感妆容'])}，自然挂小黄车"
            title = f"{original}×美妆｜{random.choice(['这3支口红必入', '5分钟打造同款氛围感', '偷师明星化妆师'])}"
            tags = ["#跨界借势", "#氛围感"]
        recreate.append({"source": src, "original": original, "title": title, "angle": angle, "tags": tags})
    return {"ideas": ideas, "recreate": recreate}


# ============================================================
# Part B: 投资理财数据抓取
# ============================================================
def fetch_indexes() -> list:
    """大盘指数 - 新浪财经接口"""
    print("[财经] 抓取大盘指数...")
    # s_sh000001=上证  s_sz399001=深证  s_sz399006=创业板
    codes = [("sh000001", "上证指数"), ("sz399001", "深证成指"), ("sz399006", "创业板指")]
    indexes = []
    for code, name in codes:
        try:
            url = f"https://hq.sinajs.cn/list=s_{code}"
            headers = {"Referer": "https://finance.sina.com.cn"}
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                # 格式: var s_sh000001="上证指数,3100.12,12.34,0.40,123456,78900";
                m = re.search(r'"([^"]+)"', res.text)
                if m:
                    parts = m.group(1).split(",")
                    if len(parts) >= 4:
                        indexes.append({
                            "name": parts[0],
                            "value": parts[1],
                            "change": float(parts[3])
                        })
        except Exception as e:
            print(f"  [指数 {code}] {e}", file=sys.stderr)
    return indexes


def fetch_fund_nav(code: str) -> dict:
    """单只基金净值 - 天天基金接口"""
    try:
        # 接口返回 jsonp: jsonpgz({"fundcode":"110011","name":"...","jzrq":"...","dwjz":"...","gsz":"...","gszzl":"...","gztime":"..."});
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
    """财经快讯 - 财联社 RSS / 新浪财经 RSS"""
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
                    "title": title,
                    "summary": summary,
                    "source": source,
                    "time": pub_m.group(1).strip() if pub_m else ""
                })
        except Exception as e:
            print(f"  [{source}] {e}", file=sys.stderr)
        if news:
            break  # 一个源够用
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
        print(f"[Gist] 未配置 GITHUB_TOKEN / GIST_ID，跳过推送", file=sys.stderr)
        return False
    url = f"https://api.github.com/gists/{GIST_ID}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Content-Type": "application/json"}
    payload = {"files": {filename: {"content": content}}}
    try:
        res = requests.patch(url, headers=headers, json=payload, timeout=15)
        if res.status_code == 200:
            print(f"[Gist] ✓ {filename} 已推送")
            return True
        print(f"[Gist] ✗ {res.status_code} {res.text[:200]}", file=sys.stderr)
    except Exception as e:
        print(f"[Gist] {e}", file=sys.stderr)
    return False


# ============== Main ==============
def run_hot():
    print("\n" + "=" * 60)
    print("🚀 Part A: 爆款热点抓取")
    print("=" * 60)
    hot_items = fetch_all_hot()
    print(f"\n  共抓取 {len(hot_items)} 条原始数据")
    rewritten = rewrite_with_openai(hot_items) or rewrite_with_rules(hot_items)
    output = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "track": TRACK_NAME,
        "source_count": len(hot_items),
        "raw_hot": hot_items[:30],
        "ideas": rewritten.get("ideas", [])[:10],
        "recreate": rewritten.get("recreate", [])[:10]
    }
    os.makedirs(os.path.dirname(OUTPUT_HOT), exist_ok=True)
    with open(OUTPUT_HOT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n✓ 本地: {OUTPUT_HOT}")
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
    args = parser.parse_args()

    print(f"\n🚀 宇航员创作工作台 · 每日抓取")
    print(f"   时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if not args.only or args.only == "hot":
        run_hot()
    if not args.only or args.only == "finance":
        run_finance()

    print("\n" + "=" * 60)
    print("✅ 完成！刷新工作台网页即可看到新内容")
    print("=" * 60)


if __name__ == "__main__":
    main()