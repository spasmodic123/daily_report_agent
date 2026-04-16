# 多领域资讯日报 Agent

自动抓取财经、医疗健康（可扩展 AI 等领域）各权威官网的最新文章，经过多轮 LLM 清洗与提炼，生成结构化日报并推送到钉钉。

---

## 目录

- [功能概览](#功能概览)
- [处理流程](#处理流程)
- [项目结构](#项目结构)
- [环境配置](#环境配置)
- [快速开始](#快速开始)
- [Debug / 分段运行](#debug--分段运行)
- [领域配置说明](#领域配置说明)
- [扩展新领域](#扩展新领域)

---

## 功能概览

| 功能 | 说明 |
|------|------|
| 多领域并行 | 财经、医疗健康（可扩展 AI 等） |
| 来源可靠性 | 直接从官网/权威媒体首页抓取当日最新文章，而非依赖搜索 |
| 三层去噪 | 规则预过滤 → LLM 清洗 → 域名白名单过滤 |
| 日期过滤 | LLM 强制过滤非昨日/今日的旧文章 |
| 分段调试 | 每阶段输出保存到文件，支持从任意阶段恢复运行 |
| 钉钉推送 | HMAC 签名，Markdown 格式 |

---

## 处理流程

```
Stage 1   Extract 新闻列表页
          └─ 从各域名首页/分类页提取文章链接
             ↓
Stage 2A  Tavily 深度抓取全文
          └─ 对 Stage 1 的文章 URL 批量提取正文
             ↓
Stage 2B  LLM 清洗页面噪声
          └─ 规则预过滤（导航栏/图片）+ qwen3.5-flash 清洗
             ↓
Stage 3   领域定制化结构化提炼
          └─ 每个领域独立提示词，提取事实 + 强制日期过滤
             ↓
Stage 4   域名白名单过滤
          └─ 黑名单段落删除，未知来源标注警告
             ↓
Stage 5   统一报告排版 + 推送钉钉
          └─ 三领域合并为 Markdown 日报
```

每个阶段的输入/输出自动保存到对应目录，便于调试复用。

---

## 项目结构

```
daily_report_agent/
├── index.py                  # 主流程（5 个阶段的核心逻辑）
├── domain_config.py          # 领域配置（新闻列表页 URL、提示词模板）
├── source_filter.py          # 域名白名单/黑名单（60 个白名单，24 个黑名单）
├── setting.py                # 环境变量加载（API Key 等）
├── requirements.txt          # Python 依赖
├── .env.example              # 环境变量示例（复制为 .env 填写真实值）
│
├── stage1_search/            # Stage 1 输出：文章链接列表（JSON）
├── stage2a_extract/          # Stage 2A 输出：页面全文（JSON）
├── stage2b_cleaned/          # Stage 2B 输出：清洗后正文（TXT）
├── stage3_facts/             # Stage 3 输出：结构化事实（TXT）
├── stage4_filtered/          # Stage 4 输出：过滤后事实（TXT）
├── stage5_report/            # Stage 5 输出：最终报告（MD）
│
├── test/
│   ├── test_filter.py        # 域名过滤器单元测试
│   ├── test_multi_domain.py  # 领域配置测试
│   └── test_whitelist_coverage.py  # 白名单覆盖率测试
└── docs/
    └── README.md             # 本文件
```

---

## 环境配置

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，填写真实值：

```bash
cp .env.example .env
```

`.env` 内容说明：

| 变量 | 说明 |
|------|------|
| `QWEN_API_KEY` | 阿里云百炼 API Key（用于 LLM 清洗/提炼/排版） |
| `APP_ID` | 百炼应用 ID（Stage 3、Stage 5 的主力模型） |
| `DING_ACCESS_TOKEN` | 钉钉 Webhook access_token |
| `DING_SECRET` | 钉钉安全签名密钥（加签模式） |
| `TAVILY_API_KEY` | Tavily API Key（页面 Extract） |

### 3. 需要的外部服务

- **阿里云百炼**：提供 `qwen3.5-flash`（Stage 2B 噪声清洗）和自定义应用（Stage 3/5 提炼排版）
- **Tavily**：提供 Extract API，用于深度抓取网页正文
- **钉钉自定义机器人**：加签模式，参考[官方文档](https://open.dingtalk.com/document/robots/custom-robot-access)配置

---

## 快速开始

### 完整运行

```bash
python index.py
```

运行完成后，报告会推送到钉钉，同时保存到 `stage5_report/` 目录。

---

## Debug / 分段运行

每次运行时，所有中间结果自动按时间戳保存。查看已有时间戳：

```bash
ls stage2b_cleaned/
# 输出示例：ai_cleaned_04-16-17:00:19.txt  finance_cleaned_04-16-17:00:19.txt ...
```

使用以下环境变量控制执行范围：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RESUME_FROM_STAGE` | `1` | 从第几个 Stage 开始运行 |
| `END_AT_STAGE` | `5` | 运行到第几个 Stage 结束（含） |
| `RESUME_TIMESTAMP` | 当前时间 | 加载哪个时间戳的中间结果 |

### 常用场景

```bash
# 只跑 Stage 1（抓取文章链接，看看今天能搜到什么）
END_AT_STAGE=1 python index.py

# 从 Stage 3 开始跑到底（跳过爬虫，直接用已清洗的文本）
RESUME_FROM_STAGE=3 RESUME_TIMESTAMP="04-16-17:00:19" python index.py

# 只跑 Stage 3（单独调试提炼效果）
RESUME_FROM_STAGE=3 END_AT_STAGE=3 RESUME_TIMESTAMP="04-16-17:00:19" python index.py

# 只重新排版并推送（Stage 5 用已有的过滤结果）
RESUME_FROM_STAGE=5 RESUME_TIMESTAMP="04-16-17:00:19" python index.py
```

### 各阶段文件格式

| 阶段 | 目录 | 格式 | 内容 |
|------|------|------|------|
| Stage 1 | `stage1_search/` | JSON | `[{"url": "..."}, ...]` |
| Stage 2A | `stage2a_extract/` | JSON | `[{"url", "title", "raw_content"}, ...]` |
| Stage 2B | `stage2b_cleaned/` | TXT | 多个 `【页面N】URL: ...\n正文：...` |
| Stage 3 | `stage3_facts/` | TXT | 结构化事实列表 |
| Stage 4 | `stage4_filtered/` | TXT | 过滤后的事实（与 Stage 3 同格式） |
| Stage 5 | `stage5_report/` | MD | 最终 Markdown 日报 |

---

## 领域配置说明

所有领域配置集中在 `domain_config.py` 的 `DOMAINS` 字典中。

### 配置字段

```python
"finance": {
    "name": "财经",           # 显示名称
    "icon": "💰",             # 报告中的图标
    "news_index_urls": [      # 新闻列表页 URL（Stage 1 直接抓这些页面）
        "https://www.cnbc.com/finance/",
        "https://www.yicai.com",
        # 可以添加多个，每个页面最多提取 15 篇文章链接
    ],
    "extraction_focus": "...", # 该领域的关注重点（仅作注释）
    "extraction_prompt_template": """..."""  # Stage 3 的 LLM 提示词模板
                                             # 支持 {yesterday}, {today}, {cleaned_pages_context}
}
```

### 目前启用的领域

**财经**（`finance`）
- 列表页：CNBC 财经/经济版块、第一财经、财联社、财新

**医疗健康**（`healthcare`）
- 列表页：生物谷新闻、丁香园、健康报

### 域名白名单

`source_filter.py` 中维护了约 60 个权威域名（权重 6-10）和 24 个黑名单域名。

- **白名单**（权重 10）：OpenAI、Anthropic、IMF、WHO、FDA、Nature 等顶级机构
- **白名单**（权重 6-9）：Reuters、Bloomberg、CNBC、TechCrunch、丁香园 等主流媒体
- **黑名单**：微信公众号、CSDN、Reddit、知乎、Medium 等低信噪比平台

---

## 扩展新领域

1. **在 `domain_config.py` 的 `DOMAINS` 中添加新领域**：

```python
"your_domain": {
    "name": "新领域名称",
    "icon": "🔬",
    "news_index_urls": [
        "https://example.com/news/",
        # 填入该领域权威媒体的新闻列表页
    ],
    "extraction_focus": "关注重点描述",
    "extraction_prompt_template": """任务：提炼 {yesterday} 至 {today} 期间...

网页全文内容如下：
<pages>
{cleaned_pages_context}
</pages>

请提取核心事实，每条格式：
- 事件名称：
- 事件描述：
- 发布/发生日期：
- 来源 URL：

规则：
1. 直接提取资料，不加工。
2. 缺失字段写"未提及"，不编造数据。
3. 【日期过滤】：日期明确且早于 {yesterday} 的直接跳过。
""",
}
```

2. **在 `source_filter.py` 中将该领域的权威域名加入白名单**（可选，提高过滤精度）

3. **在 `UNIFIED_REPORT_PROMPT_TEMPLATE` 中添加新领域的排版占位符**（Stage 5）

无需修改 `index.py` 的主流程逻辑。
