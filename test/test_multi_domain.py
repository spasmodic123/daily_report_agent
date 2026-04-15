"""
测试多领域配置
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
from domain_config import (
    DOMAINS,
    get_enabled_domains,
    get_all_official_sites,
    get_all_media_sites,
)


def test_domain_config():
    print("=== 测试领域配置 ===\n")

    # 测试启用的领域
    enabled = get_enabled_domains()
    print(f"启用的领域: {enabled}")
    print(f"领域数量: {len(enabled)}\n")

    # 测试每个领域的配置
    for domain_id in enabled:
        config = DOMAINS[domain_id]
        print(f"--- {config['name']} ({domain_id}) ---")
        print(f"图标: {config['icon']}")
        print(f"查询数量: {len(config['queries'])}")
        print(f"官方站点数量: {len(config['official_sites'])}")
        print(f"媒体站点数量: {len(config['media_sites'])}")
        print(f"关注重点: {config['extraction_focus']}")
        print()

    # 测试全局站点列表
    all_official = get_all_official_sites()
    all_media = get_all_media_sites()
    print(f"全局官方站点总数: {len(all_official)}")
    print(f"全局媒体站点总数: {len(all_media)}")
    print(f"全局站点总数（去重）: {len(set(all_official + all_media))}")

    print("\n=== 配置测试完成 ===")


if __name__ == "__main__":
    test_domain_config()
