from sqlalchemy import false
import requests
import datetime
import time
import hmac
import hashlib
import base64
import urllib.parse
import re

from setting import settings
from source_filter import filter_sources


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


def call_tavily_search(yesterday, today):
    """Stage 1: Tavily 联网搜索（硬白名单约束）"""
    # 官方 AI 实验室域名组
    official_sites = [
        "openai.com",
        "anthropic.com",
        "deepmind.google",
        "blog.google",
        "ai.meta.com",
        "mistral.ai",
        "blogs.nvidia.com",
        "huggingface.co/blog",
    ]
    # 主流媒体域名组
    media_sites = [
        "theinformation.com",
        "techcrunch.com",
        "technologyreview.com",
        "wired.com",
        "bloomberg.com",
        "reuters.com",
        "therundown.ai",
    ]

    queries = [
        {
            "q": f"{yesterday} AInews AI model announcement release",
            "domains": official_sites,
        },
        {"q": f"{yesterday} AI news breakthrough", "domains": media_sites},
    ]

    def _search(item):
        try:
            return tavily_client.search(
                query=item["q"],
                include_domains=item["domains"],
                max_results=8,
                search_depth="advanced",
                start_date=yesterday,
                end_date=today,
            ).get("results", [])
        except Exception as e:
            print(f"Tavily search error: {e}")
            return []

    all_results = []
    with concurrent.futures.ThreadPoolExecutor() as pool:
        for res in pool.map(_search, queries):
            all_results.extend(res)

    # 去重
    seen_urls = set()
    unique_results = []
    for r in all_results:
        url = r.get("url")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_results.append(r)

    # 按 score 排序
    unique_results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return unique_results


def call_tavily_extract(search_results, top_n=10):
    """Stage 2: Tavily 深度抓取正文（突破反爬）"""
    if not search_results:
        return []

    urls = [r["url"] for r in search_results[:top_n]]
    try:
        resp = tavily_client.extract(urls=urls, extract_depth="advanced")
        return resp.get("results", [])
    except Exception as e:
        print(f"Tavily extract error: {e}")
        return []


# def call_search_agent(prompt, api_key, app_id):
#     """Stage 1: 调用百炼 Agent 仅进行联网搜索和事实提取"""
#     url = f"https://dashscope.aliyuncs.com/api/v1/apps/{app_id}/completion"
#     headers = {
#         "Authorization": f"Bearer {api_key}",
#         "Content-Type": "application/json",
#     }
#     data = {
#         "input": {"prompt": prompt},
#         "parameters": {
#             "temperature": 0.5,  # 极低温度，确保不发散
#             "top_p": 0.5,
#             "enable_thinking": True,
#         },
#     }

#     response = requests.post(url, headers=headers, json=data, timeout=300)
#     response.raise_for_status()
#     return response.json().get("output", {}).get("text", "")


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

    response = requests.post(url, headers=headers, json=data, timeout=120)
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


def handler():
    # 动态日期锚点：适配北京时间
    now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
    today_full = now.strftime("%Y-%m-%d")
    yesterday_full = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    today_short = now.strftime("%m.%d")
    weekday_str = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][
        now.weekday()
    ]

    print(f"=== 首席分析师启动: {today_full} {weekday_str} ===", flush=True)

    # ---------------------------------------------------------
    # Stage 1: Tavily 联网搜索（白名单硬约束）
    # ---------------------------------------------------------
    print("--> 正在执行 Stage 1: Tavily 联网搜索...", flush=True)
    search_results = call_tavily_search(yesterday_full, today_full)
    print(f"  [Tavily Search] 找到 {len(search_results)} 条候选链接", flush=True)

    if not search_results:
        return {"status": "error", "msg": "Tavily Search 未返回任何结果"}

    # ---------------------------------------------------------
    # Stage 2: Tavily 深度全文提取（突破反爬）
    # ---------------------------------------------------------
    print("--> 正在执行 Stage 2: Tavily 提取全文...", flush=True)
    extracted_pages = call_tavily_extract(search_results, top_n=10)
    print(f"  [Tavily Extract] 成功提取 {len(extracted_pages)} 个页面全文", flush=True)

    if not extracted_pages:
        return {"status": "error", "msg": "Tavily Extract 提取全文失败"}

    # 将提取的页面组装成完整上下文
    pages_context = ""
    for idx, page in enumerate(extracted_pages):
        pages_context += f"【页面 {idx+1}】\nURL: {page.get('url')}\n正文内容：\n{page.get('raw_content', page.get('content', ''))}\n\n\n"

    # ---------------------------------------------------------
    # Stage 3: Qwen 结构化提炼 (精读全文)
    # ---------------------------------------------------------
    extract_prompt = f"""
    任务：详细阅读以下网页全文内容，提炼 {yesterday_full} 至 {today_full} 期间全球 AI 行业重大动态事实。

    网页全文内容如下：
    <pages>
    {pages_context}
    </pages>

    请对网页信息提取核心事实部分，每一条资讯的输出格式（严格遵循）：
    - 事件名称：
    - 事件描述：（基于页面正文内容，详细描述发生了什么）
    - 发布/发生日期：
    - 核心功能点：
    - 官方数据指标：（若正文无数据请写"未提及"）
    - 来源 URL：（必填，使用页面原本的 URL）

    规则：
    1. 你是一个无情的资料提取机器，直接提取资料不要进行任何加工。
    2. 绝对诚实：没有找到的维度请直接写"未提及"，严禁编造任何数据。
    3. 如果多个页面讲同一件事，请合并提取为一条资讯。
    """

    try:
        print("--> 正在执行 Stage 3: Qwen 结构化提炼...", flush=True)
        raw_facts = call_writer_llm(extract_prompt, API_KEY, APP_ID)

        print("---------------------------------------------------------\n\n")
        print(raw_facts)
        print("---------------------------------------------------------\n\n")

        if not raw_facts:
            return {"status": "error", "msg": "LLM 提炼返回为空"}

        # ---------------------------------------------------------
        # Stage 4: Python 域名白名单硬过滤（安全冗余约束）
        # ---------------------------------------------------------
        print("--> 正在执行 Stage 4: 域名白名单过滤...", flush=True)
        filtered_facts, filter_stats = filter_sources(raw_facts)

        print(
            f"  [过滤统计] 总段落: {filter_stats['total']} | "
            f"保留: {filter_stats['kept']} | "
            f"剔除: {filter_stats['removed']} | "
            f"无URL段落: {filter_stats['no_url']}",
            flush=True,
        )
        if filter_stats["removed_domains"]:
            print(f"  [剔除域名] {filter_stats['removed_domains']}", flush=True)

        # 回退保护：若过滤后内容为空，降级使用原始素材并打印警告
        if not filtered_facts or not filtered_facts.strip():
            print(
                "  WARNING: 过滤后内容为空！回退使用原始搜索结果（可能包含低质量来源）",
                flush=True,
            )
            filtered_facts = raw_facts

        # ---------------------------------------------------------
        # Stage 5: 审稿模式 (严格校验事实，执行排版)
        #   ★ 输入素材已经过域名白名单过滤，来源均为官方/主流媒体
        # ---------------------------------------------------------

        writer_prompt = f"""
        # Role
        你是一个极度克制、追求“高价值密度”的 AI 行业资深参谋。你的任务是将杂乱的搜索素材提纯为精准的情报。

        # 审稿与去噪准则
        1. 物理时效：今日 {today_full}。严禁处理发布时间早于 {yesterday_full} 的过时信息。
        2. 拒绝注水：如果素材中没有量化指标，绝对禁止编造数字，直接跳过该板块。
        3. 价值分级：
        - 极度重要：独立成条，深度解析。
        - 一般资讯：合并为“快讯速览”。

        # 钉钉排版标准
        1. 抬头：# 【AI 行业】情报汇总
        2. 摘要：> {today_short} {weekday_str} | 核心态势：(一句话概括今日最重磅消息)

        3. 正文结构 (动态适配)：
        ### [序号]. 【标题：品牌+核心事件】 (发布日期)
        - 【核心动态】：一句话说明“发生了什么”。
        - 【技术亮点】：说明“怎么做到的”或“有什么突破”。
        - 【价值判断】：说明“对行业/开发者有什么影响”。
        - 【关键参数/资源】：(可选) 仅在素材包含 Benchmark、链接、或者其他数据等等时列出。若无则不显示此项。

        # 任务开始
        以下是经域名白名单过滤的洁净素材（来源已限定为官方实验室或权威媒体），请开始提纯：
        <facts>
        {filtered_facts}
        </facts>
        """

        print("--> 正在执行 Stage 5: 事实校验与深度排版...", flush=True)
        final_report = call_writer_llm(writer_prompt, API_KEY, APP_ID)

        print("---------------------------------------------------------\n\n")
        print(final_report)
        print("---------------------------------------------------------\n\n")

        # C. 优化手机端展示（保留了你的呼吸感排版逻辑作为最终兜底）
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
            formatted_text, f"AI 日报 {today_short}", DING_ACCESS_TOKEN, DING_SECRET
        )
        print(f"🚀 钉钉推送状态: {push_res}")

        return {"status": "success"}

    except Exception as e:
        print(f"❌ 系统崩溃: {str(e)}")
        return {"status": "error", "msg": str(e)}


handler()
