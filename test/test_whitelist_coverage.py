"""
测试域名过滤器白名单覆盖率
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

from domain_config import get_all_official_sites, get_all_media_sites
from source_filter import WHITELIST_DOMAINS


def test_whitelist_coverage():
    print("=== 测试白名单覆盖率 ===\n")

    all_sites = set(get_all_official_sites() + get_all_media_sites())
    whitelist_sites = set(WHITELIST_DOMAINS.keys())

    print(f"配置中的站点总数: {len(all_sites)}")
    print(f"白名单中的站点总数: {len(whitelist_sites)}")

    # 检查缺失的站点
    missing = all_sites - whitelist_sites
    if missing:
        print(f"\n⚠️  白名单中缺失的站点 ({len(missing)}):")
        for site in sorted(missing):
            print(f"  - {site}")
    else:
        print("\n✅ 所有配置的站点都在白名单中")

    # 检查白名单中多余的站点（不在配置中）
    extra = whitelist_sites - all_sites
    if extra:
        print(f"\n📋 白名单中的额外站点 ({len(extra)}):")
        for site in sorted(extra):
            print(f"  - {site} (权重: {WHITELIST_DOMAINS[site]})")

    print("\n=== 测试完成 ===")


if __name__ == "__main__":
    test_whitelist_coverage()
