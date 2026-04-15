"""
test_filter.py — source_filter 单元测试脚本
运行方式：cd /Users/wuboxiong/Desktop/learn/daily_report_agent && python /tmp/test_filter.py
"""

import sys
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(script_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)
src_dir = os.path.join(root_dir, "src")
if src_dir not in sys.path:
    sys.path.append(src_dir)

from source_filter import get_domain_score, filter_sources

# ========== 测试 get_domain_score ==========
print("=" * 50)
print("【测试 1】get_domain_score 评分测试")
print("=" * 50)

cases = [
    ("https://openai.com/blog/gpt-5", 10, "✅ 白名单-精确匹配"),
    ("https://blog.openai.com/new-model", 10, "✅ 白名单-子域名匹配"),
    ("https://techcrunch.com/2024/ai-news", 8, "✅ 媒体白名单"),
    ("https://huggingface.co/papers/xxxx", 9, "✅ HuggingFace"),
    ("https://zhihu.com/p/123456", -100, "❌ 黑名单-知乎"),
    ("https://toutiao.com/group/xxx", -100, "❌ 黑名单-头条"),
    ("https://mp.weixin.qq.com/s/abc", -100, "❌ 黑名单-微信"),
    ("https://example.com/some-ai-post", 0, "⚪ 未知域名-中性"),
    ("https://www.reuters.com/technology/ai", 8, "✅ www. 前缀正确剥离"),
]

all_pass = True
for url, expected, label in cases:
    actual = get_domain_score(url)
    status = "PASS" if actual == expected else "FAIL"
    if status == "FAIL":
        all_pass = False
    print(f"  [{status}] {label}")
    print(f"         URL: {url}")
    print(f"         期望: {expected}, 实际: {actual}")
    print()

# ========== 测试 filter_sources ==========
print("=" * 50)
print("【测试 2】filter_sources 段落过滤测试")
print("=" * 50)

sample_text = """
- 事件名称：GPT-5 发布
- 事件描述：OpenAI 发布了下一代旗舰模型
- 来源 URL: https://openai.com/blog/gpt-5

- 事件名称：某知乎大V博主速报
- 事件描述：听说 GPT-5 要发布了
- 来源 URL: https://zhihu.com/p/987654321

- 事件名称：Claude 4 技术报告
- 事件描述：Anthropic 发布了 Claude 4 的技术报告
- 来源 URL: https://anthropic.com/research/claude-4

- 事件名称：AI 行业综合快讯（无URL段落）
- 事件描述：本周 AI 行业整体活跃，多家大厂发布新品。
"""

filtered, stats = filter_sources(sample_text)

print(f"\n  过滤统计：{stats}")
print(f"\n  过滤后内容：\n{'─'*40}\n{filtered}\n{'─'*40}")

# 验证知乎段落被剔除
assert "zhihu.com" not in filtered, "FAIL: 知乎段落未被剔除！"
assert "openai.com" in filtered, "FAIL: OpenAI 段落被误删！"
assert "anthropic.com" in filtered, "FAIL: Anthropic 段落被误删！"
assert "来源未知" in filtered, "FAIL: 无URL段落未被标注'来源未知'！"
assert stats["removed"] == 1, f"FAIL: 剔除数量期望 1，实际 {stats['removed']}"
print("\n  段落过滤测试：PASS ✅")

# ========== 测试回退逻辑（全黑名单） ==========
print()
print("=" * 50)
print("【测试 3】全黑名单内容 → 回退保护")
print("=" * 50)

blacklist_only = """
- 来源 URL: https://zhihu.com/p/111

- 来源 URL: https://toutiao.com/group/222
"""
filtered_b, stats_b = filter_sources(blacklist_only)
print(f"  过滤结果长度: {len(filtered_b.strip())} 字符（期望: 0）")
print(f"  统计: {stats_b}")
if len(filtered_b.strip()) == 0:
    print("  全黑名单回退测试：PASS ✅（调用方需做回退处理，过滤器正确返回空）")
else:
    print(f"  全黑名单回退测试：FAIL ❌（过滤后不为空: {filtered_b!r}）")

print()
print("=" * 50)
if all_pass:
    print("✅ 所有测试通过！")
else:
    print("❌ 存在失败测试，请检查上方输出。")
print("=" * 50)
