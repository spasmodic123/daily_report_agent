import requests
import datetime
import time
import hmac
import hashlib
import base64
import urllib.parse
import re
import json
import os


# ================= Stage I/O Helpers =================
def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def save_stage_json(folder, filename, data):
    _ensure_dir(folder)
    with open(os.path.join(folder, filename), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_stage_text(folder, filename, text):
    _ensure_dir(folder)
    with open(os.path.join(folder, filename), "w", encoding="utf-8") as f:
        f.write(text)


def load_stage_json(folder, filename):
    path = os.path.join(folder, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"[Resume] 找不到文件: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_stage_text(folder, filename):
    path = os.path.join(folder, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"[Resume] 找不到文件: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ================= URL噪声预过滤 =================
def prefilter_raw_content(raw_content: str) -> str:
    """
    在发给LLM清洗之前，用规则先去除明显的噪声：
    - 纯图片行、裸URL行：直接删除
    - 高密度链接区块（导航栏/目录）：用滑动窗口检测，整块折叠为占位符
    """
    lines = raw_content.split("\n")

    # 纯 markdown 链接行（含列表/标题前缀）
    nav_link_re = re.compile(
        r"^(\s*[\*\-#]+\s*)?\[.{0,80}\]\(https?://[^\)]{1,300}\)\s*$"
    )
    img_re = re.compile(r"^\s*!\[.*?\]\(.*?\)")
    bare_url_re = re.compile(r"^\s*https?://\S+\s*$")

    # 标记每行是否为"链接噪声行"
    is_link = []
    for line in lines:
        s = line.strip()
        if not s:
            is_link.append(False)
        elif img_re.match(s) or bare_url_re.match(s) or nav_link_re.match(s):
            is_link.append(True)
        else:
            is_link.append(False)

    # 滑动窗口检测高密度链接区块
    WINDOW = 7
    THRESHOLD = 0.65
    n = len(lines)
    in_nav_block = [False] * n
    for i in range(n - WINDOW + 1):
        window_links = sum(1 for j in range(i, i + WINDOW) if is_link[j])
        window_nonempty = sum(1 for j in range(i, i + WINDOW) if lines[j].strip())
        if window_nonempty > 0 and window_links / window_nonempty >= THRESHOLD:
            for j in range(i, i + WINDOW):
                in_nav_block[j] = True

    # 生成中间结果（None=空行，'__NAV__'=导航链接行，其余保留）
    result = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            result.append(None)
            continue
        if img_re.match(s) or bare_url_re.match(s):
            continue  # 直接删除
        if in_nav_block[i] and is_link[i]:
            result.append("__NAV__")
        else:
            result.append(line)

    # 合并连续 __NAV__ 块为单个占位符
    cleaned = []
    i = 0
    while i < len(result):
        item = result[i]
        if item == "__NAV__" or (
            item is None and i + 1 < len(result) and result[i + 1] == "__NAV__"
        ):
            j = i
            has_nav = False
            while j < len(result) and (result[j] == "__NAV__" or result[j] is None):
                if result[j] == "__NAV__":
                    has_nav = True
                j += 1
            if has_nav:
                cleaned += ["", "[...导航/目录链接已省略...]", ""]
            i = j
        else:
            cleaned.append("" if item is None else item)
            i += 1

    # 清理多余空行
    final = []
    prev_empty = False
    for line in cleaned:
        if not line:
            if not prev_empty:
                final.append(line)
            prev_empty = True
        else:
            prev_empty = False
            final.append(line)

    return "\n".join(final)


# =====================================================

from setting import settings
from source_filter import filter_sources
from domain_config import DOMAINS, get_enabled_domains, UNIFIED_REPORT_PROMPT_TEMPLATE

# ================= 1. 核心参数配置 =================
API_KEY = settings.QWEN_API_KEY
APP_ID = settings.APP_ID
# QWEN_MODEL = "qwen-max"                # 负责排版与校验的基础模型
DING_ACCESS_TOKEN = settings.DING_ACCESS_TOKEN
DING_SECRET = settings.DING_SECRET
TAVILY_API_KEY = settings.TAVILY_API_KEY

from tavily import TavilyClient
import concurrent.futures

tavily_client = TavilyClient(api_key=TAVILY_API_KEY)
# =================================================


def call_tavily_search_multi_domain(yesterday, today, enabled_domains):
    """Stage 1: 多领域并发 Tavily 联网搜索"""
    all_queries = []

    for domain_id in enabled_domains:
        domain_config = DOMAINS.get(domain_id)
        if not domain_config:
            continue

        official_sites = domain_config["official_sites"]
        media_sites = domain_config["media_sites"]

        for query_config in domain_config["queries"]:
            query_item = {
                "domain_id": domain_id,
                "q": query_config["q"],
                "domains": (
                    official_sites
                    if query_config["type"] == "official"
                    else media_sites
                ),
            }
            all_queries.append(query_item)

    def _search(item):
        try:
            return {
                "domain_id": item["domain_id"],
                "results": tavily_client.search(
                    query=item["q"],
                    include_domains=item["domains"],
                    max_results=3,
                    search_depth="advanced",
                    start_date=yesterday,
                    end_date=today,
                ).get("results", []),
            }
        except Exception as e:
            print(f"Tavily search error for {item['domain_id']}: {e}")
            return {"domain_id": item["domain_id"], "results": []}

    # 并发执行所有查询
    domain_results = {}
    with concurrent.futures.ThreadPoolExecutor() as pool:
        for res in pool.map(_search, all_queries):
            domain_id = res["domain_id"]
            if domain_id not in domain_results:
                domain_results[domain_id] = []
            domain_results[domain_id].extend(res["results"])

    # 每个领域内去重并排序
    for domain_id in domain_results:
        seen_urls = set()
        unique_results = []
        for r in domain_results[domain_id]:
            url = r.get("url")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(r)
        unique_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        domain_results[domain_id] = unique_results

    return domain_results


def call_tavily_extract(search_results, top_n=8):
    """Stage 2: Tavily 深度抓取正文（突破反爬）"""
    if not search_results:
        return []

    urls = [r["url"] for r in search_results[:top_n]]
    try:
        resp = tavily_client.extract(urls=urls, extract_depth="advanced")
        """
        {
            "results": [
                {
                    "url": "https://news.aibase.com/zh/news/27143",
                    "title": "100B 匿名模型 Elephant 冲上 OpenRouter 趋势榜第二",
                    "raw_content": "# 100B 匿名模型 Elephant 冲上 OpenRouter 趋势榜第二\n\n[![Image 1: AIBase](blob:http://localhost/64067b386f7258a8d203b80b0ead7a72)](https://www.aibase.com/)\n\n[首页](https://www.aibase.com/zh)\n\n[AI资讯](https://news.aibase.com/zh)\n\n[AI产品库](https://app.aibase.com/zh)\n\n[GEO平台](https://news.aibase.com/zh/news/27143)\n\n[MCP服务](https://mcp.aibase.com/zh)\n\n[模型算力广场](https://model.aibase.com/zh)\n\nZH\n\n登录/注册\n\n登录/注册\n\n[AI资讯](https://news.aibase.com/zh)\n\n[AI新闻资讯](https://news.aibase.com/zh/news)\n\n正文\n\n# 100B 匿名模型 Elephant 冲上 OpenRouter 趋势榜第二\n\n![Image 2: aibase](https://news.aibase.com/_nuxt/userlogo.q1jFctRw.png)\n\n发布于AI新闻资讯\n\n发布时间 :2026年4月15号 14:35\n\n阅读 :1 分钟\n\n4月15日，OpenRouter 数据显示，上线仅一天的匿名模型 Elephant Alpha 登上平台趋势榜（Trending）第2位、日榜(Today)第13名，token 使用量日增长377%。\n\n![Image 3: 862664070ee607688263bfb46af80fa9.png](https://upload.chinaz.com/2026/0415/6391186047781884333534301.png)\n\n![Image 4: 231407e92c3b7628dfd1e3336fdd441c.png](https://upload.chinaz.com/2026/0415/6391186049074233199195447.png)\n\nElephant拥有100B 参数量，支持256K 上下文输入及32K 输出。该模型在保持与同尺寸级别 SOTA 模型相当智能水平的前提下，提供了更快的响应速度与更低的资源占用。\n\n目前，社区对该匿名模型的猜测不一，可能是国产 最新 模型的 Flash 版本，或海外全新实验室出品。\n\n### 相关推荐\n\n[## 谷歌发布全新 Windows 桌面 AI 应用，轻松两键即可搜索！ 谷歌推出Windows版AI搜索应用，用户无需浏览器即可快速搜索。内置Gemini AI技术，按Alt+Space键即可呼出界面，输入问题获取即时结果。 2026年4月15号 13:53 114.3k](https://news.aibase.com/zh/news/27139)[## 谷歌DeepMind招了一位哲学家，这个信号比任何技术发布都值得关注 谷歌DeepMind首次在头部AI实验室设立全职哲学家岗位，聘请剑桥学者Henry Shevlin，研究方向聚焦机器意识、人机关系及人类对AGI的准备。他将深度参与实际研究，而非仅挂名顾问。 2026年4月15号 11:49 133.9k](https://news.aibase.com/zh/news/27137)[## ​天猫推出新规：规范 AI 软件及应用商品发布体验 天猫发布新规，要求商家在发布AI软件及应用类商品时，必须将其归类于指定目录，并确保产品信息真实透明。新规已于2026年4月14日正式生效，旨在提升消费者购物体验。 2026年4月15号 11:33 132.9k](https://news.aibase.com/zh/news/27135)[## OpenAI 投资者因 Anthropic 崛起而重新审视投资策略 《金融时报》报道称，OpenAI高达8520亿美元的估值正引发投资者质疑，主要因其面临Anthropic的激烈竞争。Anthropic年化收入从2025年底的90亿美元猛增至2026年3月的300亿美元，增长动力来自其编码工具需求强劲。有同时投资两家公司的投资者指出，OpenAI近期融资的合理性假设面临挑战。 2026年4月15号 10:42 149.8k](https://news.aibase.com/zh/news/27132)[## AI眼镜进入爆发期:千问旗舰款眼镜S1开售，苹果传明年上市 4月15日，千问AI眼镜S1正式开售，标志着AI眼镜市场进入爆发期。今年AI眼镜增速达智能眼镜整体市场的8倍，千问首款产品G1于3月上市即获超70%线上份额。Meta年出货近800万台，阿里等AI企业已占据市场第一梯队。华为、苹果虽传将入局，但尚未正式发布产品。 2026年4月15号 10:21 157.3k](https://news.aibase.com/zh/news/27129)\n\n![Image 5: AIBase](blob:http://localhost/64067b386f7258a8d203b80b0ead7a72)\n\n智启未来，您的人工智能解决方案智库\n\n[English](https://news.aibase.com/news/27143)[简体中文](https://news.aibase.com/zh/news/27143)[繁體中文](https://news.aibase.com/tw/news/27143)[にほんご](https://news.aibase.com/ja/news/27143)\n\n© 2026 AIBase",
                    "images": []
                },
                ...
            ],
            "failed_results": [],
            "response_time": 9.73,
            "request_id": "77c01f4d-fbc4-465a-88fe-8a0179b912c7"
        }
        """
        return resp.get("results", [])
    except Exception as e:
        print(f"Tavily extract error: {e}")
        return []


def call_writer_llm(prompt, api_key, app_id):
    """Stage 2: 调用基础模型进行事实清洗与排版 (兼容 OpenAI 接口规范)"""
    url = f"https://dashscope.aliyuncs.com/api/v1/apps/{app_id}/completion"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = {
        "input": {"prompt": prompt},
        "parameters": {"temperature": 0.5, "top_p": 0.5, "enable_thinking": False},
    }

    response = requests.post(url, headers=headers, json=data, timeout=360)
    response.raise_for_status()
    return response.json().get("output", {}).get("text", "")
    # return response.json().get("choices", [{}])[0].get("message", {}).get("content", "")


def push_to_dingtalk(text, title, access_token, secret):
    """将最终内容推送到钉钉"""
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256
    ).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    target_url = f"https://oapi.dingtalk.com/robot/send?access_token={access_token}&timestamp={timestamp}&sign={sign}"

    res = requests.post(
        target_url,
        json={"msgtype": "markdown", "markdown": {"title": title, "text": text}},
        timeout=20,
    )
    return res.text


def handler(resume_config=None):
    # 动态日期锚点：适配北京时间
    now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
    today_full = now.strftime("%Y-%m-%d")
    yesterday_full = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    today_short = now.strftime("%m.%d")
    weekday_str = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][
        now.weekday()
    ]
    today_minute = now.strftime("%m-%d-%H:%M:%S")

    # Debug / Resume 配置
    start_from = 1
    end_at = 5
    resume_ts = today_minute

    if resume_config:
        start_from = resume_config.get("start_from", 1)
        end_at = resume_config.get("end_at", 5)
        resume_ts = resume_config.get("timestamp") or today_minute
        print(
            f"[Debug] Stage {start_from} → {end_at}，加载时间戳: {resume_ts}",
            flush=True,
        )

    ts = today_minute  # 本次运行保存文件用的时间戳

    print(f"=== 多领域资讯分析师启动: {today_full} {weekday_str} ===", flush=True)

    # 获取启用的领域
    enabled_domains = get_enabled_domains()
    print(f"启用的领域: {[DOMAINS[d]['name'] for d in enabled_domains]}", flush=True)

    # ---------------------------------------------------------
    # Stage 1: 多领域并发 Tavily 联网搜索
    # ---------------------------------------------------------
    print("--> 正在执行 Stage 1: 多领域 Tavily 联网搜索...", flush=True)
    print(f"yesterday_full: {yesterday_full}", flush=True)
    print(f"today_full: {today_full}", flush=True)

    if start_from <= 1 <= end_at:
        domain_search_results = call_tavily_search_multi_domain(
            yesterday_full, today_full, enabled_domains
        )
        for domain_id, results in domain_search_results.items():
            save_stage_json("stage1_search", f"{domain_id}_search_{ts}.json", results)
            print(
                f"  [Tavily Search] {DOMAINS[domain_id]['name']}: 找到 {len(results)} 条候选链接",
                flush=True,
            )
        print(f"  [Saved] stage1_search/", flush=True)
    else:
        print(f"  [Resume] 加载 Stage 1 结果 (ts={resume_ts})...", flush=True)
        domain_search_results = {}
        for d in enabled_domains:
            domain_search_results[d] = load_stage_json(
                "stage1_search", f"{d}_search_{resume_ts}.json"
            )
            print(
                f"  [Loaded] {DOMAINS[d]['name']}: {len(domain_search_results[d])} 条",
                flush=True,
            )

    if end_at < 2:
        print("[Debug] end_at=1，已完成 Stage 1，退出。", flush=True)
        return {"status": "debug_exit", "stage": 1}

    if not any(domain_search_results.values()):
        return {"status": "error", "msg": "所有领域的 Tavily Search 均未返回结果"}

    # ---------------------------------------------------------
    # Stage 2-4: 按领域处理（提取、清洗、提炼、过滤）
    # ---------------------------------------------------------
    domain_filtered_facts = {}

    for domain_id in enabled_domains:
        # 讲一个domain全部处理完再处理下一个stage
        search_results = domain_search_results.get(domain_id, [])
        if not search_results and start_from <= 2:
            print(f"[{DOMAINS[domain_id]['name']}] 无搜索结果，跳过", flush=True)
            domain_filtered_facts[domain_id] = "今日暂无重大动态"
            continue

        print(
            f"\n--> 正在处理领域: {DOMAINS[domain_id]['name']} ({domain_id})",
            flush=True,
        )

        # Stage 2A: Tavily 深度全文提取
        if start_from <= 2 <= end_at:
            print(f"  [Stage 2A] 提取全文...", flush=True)
            extracted_pages = call_tavily_extract(search_results, top_n=10)
            print(
                f"  domain {DOMAINS[domain_id]['name']} ,成功提取 {len(extracted_pages)} 个页面全文",
                flush=True,
            )
            save_stage_json(
                "stage2a_extract", f"{domain_id}_extract_{ts}.json", extracted_pages
            )

            if not extracted_pages:
                print(f"  [{DOMAINS[domain_id]['name']}] 提取失败，跳过", flush=True)
                domain_filtered_facts[domain_id] = "今日暂无重大动态"
                continue
        elif start_from > 2:
            print(f"  [Resume] 加载 Stage 2A 结果 (ts={resume_ts})...", flush=True)
            extracted_pages = load_stage_json(
                "stage2a_extract", f"{domain_id}_extract_{resume_ts}.json"
            )
            print(f"  [Loaded] {len(extracted_pages)} 个页面", flush=True)

        # Stage 2B: LLM 清洗页面噪声
        if start_from <= 2 <= end_at:
            print(f"  [Stage 2B] 清洗页面噪声...", flush=True)

            def _clean_page(idx, page):
                url = page.get("url")
                raw_content = page.get("raw_content", page.get("content", ""))

                # 规则预过滤：去除导航栏/图片/裸URL等噪声，降低发给LLM的token量
                raw_content = prefilter_raw_content(raw_content)

                if len(raw_content) > 40000:
                    raw_content = raw_content[:40000] + "\n...(因过长截断)"

                clean_prompt = f"""任务：清理以下网页的垃圾噪声。去除所有长篇幅的 base64 编码图片、无用 svg/html 样式代码、页脚导航栏等干扰。
            \n只保留真正有用的新闻报道正文、技术说明、引述等纯文本内容。\n请直接输出清理后的干净正文，不要输出多余格式或者前置提示：\n\n{raw_content}"""

                api_url = (
                    "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
                )
                headers = {
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json",
                }
                data = {
                    "model": "qwen3.5-flash",
                    "messages": [{"role": "user", "content": clean_prompt}],
                    "temperature": 0.5,
                }

                try:
                    resp = requests.post(
                        api_url, headers=headers, json=data, timeout=360
                    )
                    resp.raise_for_status()
                    cleaned_content = (
                        resp.json()
                        .get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    )
                    if not cleaned_content.strip():
                        cleaned_content = raw_content
                except Exception as e:
                    print(f"  [警告] 页面 {idx+1} 清洗失败: {e}", flush=True)
                    cleaned_content = raw_content

                return f"【页面 {idx+1}】\nURL: {url}\n正文内容（已清洗）：\n{cleaned_content}\n\n\n"

            cleaned_pages_context_list = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
                results = pool.map(
                    lambda enum: _clean_page(enum[0], enum[1]),
                    enumerate(extracted_pages),
                )
                cleaned_pages_context_list = list(results)

            cleaned_pages_context = "".join(cleaned_pages_context_list)

            try:
                save_stage_text(
                    "stage2b_cleaned",
                    f"{domain_id}_cleaned_{ts}.txt",
                    cleaned_pages_context,
                )
            except Exception as e:
                print(f"  [Debug] 保存 {domain_id} 清洗结果失败: {e}", flush=True)

        elif start_from > 2:
            print(f"  [Resume] 加载 Stage 2B 结果 (ts={resume_ts})...", flush=True)
            cleaned_pages_context = load_stage_text(
                "stage2b_cleaned", f"{domain_id}_cleaned_{resume_ts}.txt"
            )

        if end_at < 3:
            print(
                f"  [Debug] end_at=2，已完成 Stage 2B for {domain_id}，跳过后续。",
                flush=True,
            )
            continue

        # Stage 3: 领域定制化提炼
        try:
            if start_from <= 3 <= end_at:
                print(f"  [Stage 3] 结构化提炼...", flush=True)
                domain_config = DOMAINS[domain_id]
                extract_prompt = domain_config["extraction_prompt_template"].format(
                    yesterday=yesterday_full,
                    today=today_full,
                    cleaned_pages_context=cleaned_pages_context,
                )
                raw_facts = call_writer_llm(extract_prompt, API_KEY, APP_ID)
                if not raw_facts:
                    print(
                        f"  [{DOMAINS[domain_id]['name']}] LLM 提炼返回为空", flush=True
                    )
                    domain_filtered_facts[domain_id] = "今日暂无重大动态"
                    continue
                save_stage_text(
                    "stage3_facts", f"{domain_id}_facts_{ts}.txt", raw_facts
                )
            else:
                print(f"  [Resume] 加载 Stage 3 结果 (ts={resume_ts})...", flush=True)
                raw_facts = load_stage_text(
                    "stage3_facts", f"{domain_id}_facts_{resume_ts}.txt"
                )

            if end_at < 4:
                print(
                    f"  [Debug] end_at=3，已完成 Stage 3 for {domain_id}，跳过后续。",
                    flush=True,
                )
                continue

            # Stage 4: 域名白名单过滤
            if start_from <= 4 <= end_at:
                print(f"  [Stage 4] 域名白名单过滤...", flush=True)
                filtered_facts, filter_stats = filter_sources(raw_facts)
                print(
                    f"  [过滤统计] 总段落: {filter_stats['total']} | "
                    f"保留: {filter_stats['kept']} | "
                    f"剔除: {filter_stats['removed']}",
                    flush=True,
                )
                if not filtered_facts or not filtered_facts.strip():
                    print(
                        f"  WARNING: {DOMAINS[domain_id]['name']} 过滤后内容为空！回退使用原始搜索结果（可能包含低质量来源）",
                        flush=True,
                    )
                    filtered_facts = raw_facts
                save_stage_text(
                    "stage4_filtered", f"{domain_id}_filtered_{ts}.txt", filtered_facts
                )
            else:
                print(f"  [Resume] 加载 Stage 4 结果 (ts={resume_ts})...", flush=True)
                filtered_facts = load_stage_text(
                    "stage4_filtered", f"{domain_id}_filtered_{resume_ts}.txt"
                )

            domain_filtered_facts[domain_id] = filtered_facts

        except Exception as e:
            print(f"  [{DOMAINS[domain_id]['name']}] 处理失败: {e}", flush=True)
            domain_filtered_facts[domain_id] = "今日暂无重大动态"

    # ---------------------------------------------------------
    # Stage 5: 统一报告排版与推送
    # ---------------------------------------------------------
    print("\n--> 正在执行 Stage 5: 统一报告排版...", flush=True)

    if end_at < 5:
        print("[Debug] end_at < 5，跳过 Stage 5（不推送钉钉）", flush=True)
        return {"status": "debug_exit", "stage": end_at}

    try:
        writer_prompt = UNIFIED_REPORT_PROMPT_TEMPLATE.format(
            today_full=today_full,
            yesterday_full=yesterday_full,
            today_short=today_short,
            weekday_str=weekday_str,
            ai_facts=domain_filtered_facts.get("ai", "今日暂无重大动态"),
            finance_facts=domain_filtered_facts.get("finance", "今日暂无重大动态"),
            healthcare_facts=domain_filtered_facts.get(
                "healthcare", "今日暂无重大动态"
            ),
        )

        final_report = call_writer_llm(writer_prompt, API_KEY, APP_ID)

        save_stage_text("stage5_report", f"report_{ts}.md", final_report)

        print("---------------------------------------------------------\n\n")
        print("final_report: \n", final_report)
        print("---------------------------------------------------------\n\n")

        # 优化手机端展示
        lines = [l.strip() for l in final_report.split("\n") if l.strip()]
        formatted_text = ""
        for l in lines:
            if l.startswith("#") or l.startswith("---"):
                formatted_text += f"\n\n{l}\n\n"
            elif l.startswith(">"):
                formatted_text += f"{l}\n\n"
            elif l.startswith("- **") or l.startswith("- "):
                formatted_text += f"{l}\n"
            else:
                formatted_text += f"{l}\n\n"

        # 清理可能残留的引用标签
        formatted_text = re.sub(r"\[\^\d+\]", "", formatted_text)
        formatted_text = re.sub(r"\n{3,}", "\n\n", formatted_text).strip()

        print("-> 正在推送至钉钉...", flush=True)
        push_res = push_to_dingtalk(
            formatted_text,
            f"综合资讯日报 {today_short}",
            DING_ACCESS_TOKEN,
            DING_SECRET,
        )
        print(f"🚀 钉钉推送状态: {push_res}")

        return {"status": "success"}

    except Exception as e:
        print(f"❌ 系统崩溃: {str(e)}")
        return {"status": "error", "msg": str(e)}


if __name__ == "__main__":
    _start = int(os.environ.get("RESUME_FROM_STAGE", "1") or "1")
    _end = int(os.environ.get("END_AT_STAGE", "5") or "5")
    _ts = os.environ.get("RESUME_TIMESTAMP", "").strip() or None
    if _start > 1 or _end < 5:
        handler(resume_config={"start_from": _start, "end_at": _end, "timestamp": _ts})
    else:
        handler()
