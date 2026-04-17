"""
domain_config.py — 多领域配置中心

职责：
    - 定义各领域的搜索查询词、域名白名单
    - 提供领域特定的提示词模板
    - 支持配置驱动的多领域扩展

使用方式：
    from domain_config import DOMAINS, get_enabled_domains
"""

# ===========================================================
# 领域配置字典
# ===========================================================
DOMAINS = {
    "ai": {
        "name": "AI行业",
        "icon": "🤖",
        "rss_urls": [
            # 填入有 RSS feed 的权威媒体 URL，优先使用（时序最准确）
            # "https://techcrunch.com/category/artificial-intelligence/feed/",
        ],
        "news_index_urls": [
            "https://news.aibase.cn/news",
            # "https://techcrunch.com/",
        ],
        "extraction_focus": "AI模型发布、技术突破、融资动态、Benchmark数据",
        "extraction_prompt_template": """任务：详细阅读以下网页全文内容，提炼 {yesterday} 至 {today} 期间全球 AI 行业重大动态事实。

网页全文内容如下：
<pages>
{cleaned_pages_context}
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
4. 【日期过滤 - 最高优先级】：每条资讯必须先判断其发布/发生日期。若日期明确且早于 {yesterday} 或晚于 {today}，直接跳过该条，不输出任何内容。若页面中完全找不到日期信息，保留该条但在发布/发生日期字段注明"日期不明"。
""",
    },
    "finance": {
        "name": "财经",
        "icon": "💰",
        "rss_urls": [
            # CNBC 有官方 RSS，但需在真实环境验证可达性
            # "https://www.cnbc.com/id/10000664/device/rss/rss.html",
        ],
        "news_index_urls": [
            "https://www.cnbc.com/finance/",
            # "https://www.cnbc.com/economy/",
            # "https://www.yicai.com",
            # "https://www.cls.cn",
            # "https://www.caixin.com",
        ],
        "extraction_focus": "股市波动、金融政策、企业财报、并购IPO、宏观经济数据",
        "extraction_prompt_template": """任务：详细阅读以下网页全文内容，提炼 {yesterday} 至 {today} 期间全球财经动态事实。

网页全文内容如下：
<pages>
{cleaned_pages_context}
</pages>

关注重点：
- 股市重大波动（涨跌超5%）
- 金融政策变化（央行利率、监管新规）
- 企业财报（营收、利润、市值变化）
- 并购/IPO事件
- 宏观经济数据（GDP、CPI、失业率）

请对网页信息提取核心事实部分，每一条资讯的输出格式（严格遵循）：
- 事件名称：
- 事件描述：（基于页面正文内容，详细描述发生了什么）
- 发布/发生日期：
- 关键数据：（股价、金额、百分比等，若无数据请写"未提及"）
- 影响分析：（对市场/行业的影响，若无分析请写"未提及"）
- 来源 URL：（必填，使用页面原本的 URL）

规则：
1. 你是一个无情的资料提取机器，直接提取资料不要进行任何加工。
2. 绝对诚实：没有找到的维度请直接写"未提及"，严禁编造任何数据。
3. 如果多个页面讲同一件事，请合并提取为一条资讯。
4. 【日期过滤 - 最高优先级】：每条资讯必须先判断其发布/发生日期。若日期明确且早于 {yesterday} 或晚于 {today}，直接跳过该条，不输出任何内容。若页面中完全找不到日期信息，保留该条但在发布/发生日期字段注明"日期不明"。
""",
    },
    "healthcare": {
        "name": "医疗健康",
        "icon": "🏥",
        "rss_urls": [
            # 填入有 RSS feed 的权威医疗媒体 URL
        ],
        "news_index_urls": [
            "https://news.bioon.com",
            # "https://www.dxy.cn",
            # "https://www.jkb.com.cn",
        ],
        "extraction_focus": "医学突破、临床试验、新药获批、公共卫生事件、医疗器械创新",
        "extraction_prompt_template": """任务：详细阅读以下网页全文内容，提炼 {yesterday} 至 {today} 期间全球医疗健康动态事实。

网页全文内容如下：
<pages>
{cleaned_pages_context}
</pages>

关注重点：
- 医学突破（新疗法、新技术）
- 临床试验结果（Phase I/II/III）
- 新药获批（FDA/NMPA批准）
- 公共卫生事件（疫情、政策）
- 医疗器械创新

请对网页信息提取核心事实部分，每一条资讯的输出格式（严格遵循）：
- 事件名称：
- 事件描述：（基于页面正文内容，详细描述发生了什么）
- 发布/发生日期：
- 临床数据：（有效率、安全性等，若无数据请写"未提及"）
- 适应症/目标疾病：（若无请写"未提及"）
- 来源 URL：（必填，使用页面原本的 URL）

规则：
1. 你是一个无情的资料提取机器，直接提取资料不要进行任何加工。
2. 绝对诚实：没有找到的维度请直接写"未提及"，严禁编造任何数据。
3. 如果多个页面讲同一件事，请合并提取为一条资讯。
4. 【日期过滤 - 最高优先级】：每条资讯必须先判断其发布/发生日期。若日期明确且早于 {yesterday} 或晚于 {today}，直接跳过该条，不输出任何内容。若页面中完全找不到日期信息，保留该条但在发布/发生日期字段注明"日期不明"。
""",
    },
}


# ===========================================================
# 统一报告排版提示词模板
# ===========================================================
UNIFIED_REPORT_PROMPT_TEMPLATE = """
# Role
你是一个多领域资深分析师，负责将AI、财经、医疗健康三个领域的资讯整合为统一日报。

# 审稿与排版准则
1. 物理时效：今日 {today_full}。严禁展现发生早于 {yesterday_full} 的过时信息。
2. 价值分级与合并：
   - 极度重要（行业巨头发布、技术重大突破）：独立成条，深度解析。
   - 一般资讯（小额融资、常规更新）：合并为一个"快讯速览"专区。
3. 忠于原文：基于提供的核心功能点和数据指标，直接转化为排版语言，禁止编造素材里没有的 URL 或数据。

# 钉钉排版标准
1. 抬头：# 【综合资讯】日报
2. 摘要：> {today_short} {weekday_str} | 今日覆盖：AI、财经、医疗健康

3. 分领域展示：
## 🤖 AI行业
### [序号]. 【标题：品牌+核心事件】
- **核心动态**：(基于事件描述，一句话简明扼要)
- **事件详细**：基于事实清单的详细事件描述
- **技术/商业亮点**：(基于功能点，说明"有什么突破"或"影响")
- **关键数据**：(仅在素材包含具体 Benchmark 或其他数据指标时列出，若无则跳过该行)
- **来源链接**：[查看原文](素材中的真实URL)

## 💰 财经
### [序号]. 【标题】
- **核心动态**：...
- **关键数据**：...
- **来源链接**：[查看原文](URL)

## 🏥 医疗健康
### [序号]. 【标题】
- **核心动态**：...
- **临床数据**：...
- **来源链接**：[查看原文](URL)

# 领域优先级
- 极度重要事件（行业巨头、重大突破）：置于该领域顶部
- 一般资讯：按时间倒序排列
- 若某领域当日无重要资讯，显示"今日暂无重大动态"

# 任务开始
以下是各领域经提纯过滤的结构化事实清单（来源均可靠），请开始排版：

<ai_facts>
{ai_facts}
</ai_facts>

<finance_facts>
{finance_facts}
</finance_facts>

<healthcare_facts>
{healthcare_facts}
</healthcare_facts>
"""


# ===========================================================
# 辅助函数
# ===========================================================
def get_enabled_domains():
    """返回启用的领域列表（默认全部启用）"""
    return list(DOMAINS.keys())


def get_domain_config(domain_id: str) -> dict:
    """获取指定领域的配置"""
    return DOMAINS.get(domain_id, {})


def get_all_official_sites() -> list[str]:
    """获取所有领域的官方站点（用于白名单）"""
    sites = []
    for domain in DOMAINS.values():
        sites.extend(domain.get("official_sites", []))
    return list(set(sites))


def get_all_media_sites() -> list[str]:
    """获取所有领域的媒体站点（用于白名单）"""
    sites = []
    for domain in DOMAINS.values():
        sites.extend(domain.get("media_sites", []))
    return list(set(sites))
