"""
source_filter.py — 域名白名单硬过滤器

职责：
    - 维护 AI 行业官方/主流媒体域名白名单（带权重分）
    - 维护低质量自媒体聚合站黑名单（直接剔除）
    - 按段落粒度对大模型搜索结果进行评分过滤
    - 无 URL 段落默认保留，并在内容中标注"来源未知"

使用方式：
    from source_filter import filter_sources
    filtered_text, stats = filter_sources(raw_text)
"""

import re
from urllib.parse import urlparse

# ===========================================================
# 1. 白名单域名（官方/主流媒体，带质量权重）
# ===========================================================
WHITELIST_DOMAINS: dict[str, int] = {
    # ---- 顶尖 AI 实验室（权重最高） ----
    "openai.com": 10,
    "anthropic.com": 10,
    "deepmind.google": 10,
    "blog.google": 10,
    "ai.meta.com": 10,
    "research.google": 10,
    "mistral.ai": 10,
    "groq.com": 9,
    "blogs.nvidia.com": 9,
    "developer.nvidia.com": 9,
    "huggingface.co": 9,
    "microsoft.com": 8,  # 含 /en-us/research 等子路径
    # ---- 主流科技与商业媒体 ----
    "theinformation.com": 9,
    "techcrunch.com": 8,
    "theverge.com": 8,
    "technologyreview.com": 8,
    "bloomberg.com": 8,
    "reuters.com": 8,
    "wired.com": 7,
    "therundown.ai": 7,
    # ---- 综合科技媒体（次级，仍可信） ----
    "venturebeat.com": 6,
    "zdnet.com": 6,
    "arstechnica.com": 6,
    "businessinsider.com": 6,
    "ft.com": 7,
    "wsj.com": 7,
    "cnbc.com": 6,
    # ---- 国内媒体（次级，仍可信） ----
    "zhihu.com": 6,
    "toutiao.com": 6,
    "aibase.cn": 7,
    "36kr.com": 6,
    # ---- 财经领域官方机构 ----
    "imf.org": 10,
    "worldbank.org": 10,
    "federalreserve.gov": 10,
    "ecb.europa.eu": 10,
    "pbc.gov.cn": 10,
    "csrc.gov.cn": 10,
    "sse.com.cn": 9,
    "szse.cn": 9,
    # ---- 财经媒体 ----
    "caixin.com": 8,
    "yicai.com": 8,
    "cls.cn": 7,
    "eastmoney.com": 6,
    "finance.sina.com.cn": 6,
    # ---- 医疗健康官方机构 ----
    "who.int": 10,
    "nih.gov": 10,
    "fda.gov": 10,
    "cdc.gov": 10,
    "nature.com": 10,
    "nejm.org": 10,
    "thelancet.com": 10,
    "nhc.gov.cn": 10,
    "nmpa.gov.cn": 10,
    "chinacdc.cn": 9,
    # ---- 医疗健康媒体 ----
    "statnews.com": 8,
    "medpagetoday.com": 7,
    "dxy.cn": 7,
    "cn-healthcare.com": 7,
    "yxj.org.cn": 7,
    "bioon.com": 6,
}

# ===========================================================
# 2. 黑名单域名（低质量自媒体/聚合站，直接剔除）
# ===========================================================
BLACKLIST_DOMAINS: set[str] = {
    # 国内自媒体 / 聚合站
    "weixin.qq.com",
    "mp.weixin.qq.com",
    "juejin.cn",
    "csdn.net",
    "51cto.com",
    "oschina.net",
    "segmentfault.com",
    "infoq.cn",
    "36kr.com",
    "leiphone.com",
    "jiqizhixin.com",  # 国内二手转载为主
    "sohu.com",
    "sina.com.cn",
    "163.com",
    "qq.com",
    "baidu.com",
    # 境外低质量聚合站
    "medium.com",  # 质量参差不齐，需谨慎（可按需移至白名单）
    "substack.com",  # 个人 Newsletter，可按需移至白名单
    "reddit.com",
    "twitter.com",
    "x.com",
    "linkedin.com",
    "facebook.com",
    "quora.com",
    "hackernews.com",
    "news.ycombinator.com",
}


def _extract_domain(url: str) -> str:
    """从 URL 中提取主域名（去除 www. 前缀）"""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        # 去除 www. 前缀
        if hostname.startswith("www."):
            hostname = hostname[4:]
        return hostname.lower()
    except Exception:
        return ""


def _find_urls_in_text(text: str) -> list[str]:
    """从文本中提取所有 URL"""
    url_pattern = re.compile(
        r"https?://[^\s\)\]\>\"\'，,。、；：]+",
        re.IGNORECASE,
    )
    return url_pattern.findall(text)


def get_domain_score(url: str) -> int:
    """
    返回 URL 对应域名的质量分数：
        >= 1  : 白名单域名（分数越高越优质）
        0     : 未知域名（中性，不过滤）
        -100  : 黑名单域名（直接剔除）
    """
    domain = _extract_domain(url)
    if not domain:
        return 0  # 无法解析的 URL，中性处理

    # 精确匹配黑名单（优先检查）
    if domain in BLACKLIST_DOMAINS:
        return -100

    # 精确匹配白名单
    if domain in WHITELIST_DOMAINS:
        return WHITELIST_DOMAINS[domain]

    # 子域名匹配（如 blog.openai.com → openai.com）
    parts = domain.split(".")
    for i in range(1, len(parts)):
        parent = ".".join(parts[i:])
        if parent in WHITELIST_DOMAINS:
            return WHITELIST_DOMAINS[parent]
        if parent in BLACKLIST_DOMAINS:
            return -100

    return 0  # 未知来源，中性


def _score_paragraph(paragraph: str) -> tuple[int, list[str]]:
    """
    对单个段落打分：
        返回 (最低分, 该段落中所有 URL 列表)
        - 只要段落中有任意一个黑名单 URL，整段得 -100
        - 有白名单 URL 则取最高分
        - 无 URL 则得 0（中性，保留）
    """
    urls = _find_urls_in_text(paragraph)
    if not urls:
        return 0, []  # 无 URL：中性，保留

    scores = [get_domain_score(u) for u in urls]
    min_score = min(scores)
    max_score = max(scores)

    # 任意黑名单 URL → 整段剔除
    if min_score <= -100:
        return -100, urls

    return max_score, urls


def filter_sources(raw_text: str) -> tuple[str, dict]:
    """
    主过滤函数：按段落粒度对搜索原文进行域名白名单过滤。

    Args:
        raw_text: 大模型搜索阶段返回的原始文本（多条资讯，用空行分隔）

    Returns:
        filtered_text: 过滤后的洁净文本
        stats: 过滤统计信息字典，包含：
            - total: 总段落数
            - kept: 保留段落数
            - removed: 剔除段落数
            - no_url: 无 URL 段落数（均被保留）
            - removed_domains: 被剔除的域名列表
    """
    if not raw_text or not raw_text.strip():
        return raw_text, {
            "total": 0,
            "kept": 0,
            "removed": 0,
            "no_url": 0,
            "removed_domains": [],
        }

    # 按连续空行分割为段落
    paragraphs = re.split(r"\n\s*\n", raw_text.strip())

    kept_paragraphs: list[str] = []
    removed_count = 0
    no_url_count = 0
    removed_domains: list[str] = []

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        score, urls = _score_paragraph(para)

        if score <= -100:
            # 黑名单段落：剔除，记录域名
            removed_count += 1
            for u in urls:
                d = _extract_domain(u)
                if d and d not in removed_domains:
                    removed_domains.append(d)
            print(
                f"  [过滤器] ❌ 已剔除段落（来源: {[_extract_domain(u) for u in urls]}）"
            )
        else:
            if not urls:
                no_url_count += 1
                # 无 URL 段落：保留并追加标注
                kept_paragraphs.append(para + "\n  > ⚠️ 来源未知，请降低参考权重")
            else:
                kept_paragraphs.append(para)

    filtered_text = "\n\n".join(kept_paragraphs)

    stats = {
        "total": len(paragraphs),
        "kept": len(kept_paragraphs),
        "removed": removed_count,
        "no_url": no_url_count,
        "removed_domains": removed_domains,
    }

    return filtered_text, stats
