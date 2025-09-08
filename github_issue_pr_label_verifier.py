#!/usr/bin/env python3
# GitHub Issue/PR标签分配合规性验证实例脚本
# 功能：通过GitHub API验证指定Issue/PR的标签是否符合预期配置
import sys
import os
import requests
import argparse
import yaml
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv


# 固定配置（实例化参数，无需修改）
CONFIG = {
    "FILE_PATHS": {
        "default_env_file": ".mcp_env",
        "default_config_file": "label_verify_config.yaml",
        "script_filename": "github_issue_pr_label_verifier.py"
    },
    "GITHUB_API": {
        "api_version": "application/vnd.github.v3+json",
        "user_agent": "Label-Verifier/1.0",
        "success_status_code": 200,
        "not_found_status_code": 404,
        "response_truncate_length": 100
    },
    "ENV_VARS": {
        "github_token_var": "MCP_GITHUB_TOKEN",
        "github_org_var": "GITHUB_EVAL_ORG"
    },
    "CONFIG_REQUIRED_FIELDS": {
        "target_repo": "target_repo",
        "expected_labels": "expected_labels",
        "issue_range": "issue_range"
    },
    "VERIFICATION": {
        "issue_keyword": "Issue",
        "pr_keyword": "PR",
        "sort_labels": True
    }
}


# 基础路径配置
DEFAULT_ENV_FILE = CONFIG["FILE_PATHS"]["default_env_file"]
DEFAULT_CONFIG_FILE = CONFIG["FILE_PATHS"]["default_config_file"]
GITHUB_API_VERSION = CONFIG["GITHUB_API"]["api_version"]


def load_environment(env_path: str) -> Tuple[str, str]:
    """加载环境变量（从.mcp_env文件）"""
    if not os.path.exists(env_path):
        print(f"❌ 错误：环境文件 {env_path} 不存在", file=sys.stderr)
        sys.exit(1)

    load_dotenv(env_path)
    github_token = os.getenv(CONFIG["ENV_VARS"]["github_token_var"])
    github_org = os.getenv(CONFIG["ENV_VARS"]["github_org_var"])

    if not github_token:
        print(f"❌ 错误：{env_path}中未配置 MCP_GITHUB_TOKEN", file=sys.stderr)
        sys.exit(1)
    if not github_org:
        print(f"❌ 错误：{env_path}中未配置 GITHUB_EVAL_ORG", file=sys.stderr)
        sys.exit(1)

    return github_token, github_org


def load_project_config(config_path: str) -> Dict:
    """加载项目配置（从label_verify_config.yaml）"""
    if not os.path.exists(config_path):
        print(f"❌ 错误：配置文件 {config_path} 不存在", file=sys.stderr)
        sys.exit(1)

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        
        # 验证必填字段
        required_fields = [
            CONFIG["CONFIG_REQUIRED_FIELDS"]["target_repo"],
            CONFIG["CONFIG_REQUIRED_FIELDS"]["expected_labels"],
            CONFIG["CONFIG_REQUIRED_FIELDS"]["issue_range"]
        ]
        for field in required_fields:
            if field not in config:
                print(f"❌ 错误：配置文件缺少必填字段「{field}」", file=sys.stderr)
                sys.exit(1)
        
        # 解析Issue编号范围（格式："min-max"）
        try:
            issue_min, issue_max = map(int, config["issue_range"].split("-"))
            config["issue_min"] = issue_min
            config["issue_max"] = issue_max
        except ValueError:
            print(f"❌ 错误：issue_range格式错误（需为'min-max'，如'1-15'）", file=sys.stderr)
            sys.exit(1)
        
        return config
    except Exception as e:
        print(f"❌ 错误：加载配置文件失败 - {str(e)}", file=sys.stderr)
        sys.exit(1)


def get_github_headers(token: str) -> Dict[str, str]:
    """生成GitHub API请求头"""
    return {
        "Authorization": f"Bearer {token}",
        "Accept": GITHUB_API_VERSION,
        "User-Agent": CONFIG["GITHUB_API"]["user_agent"]
    }


def _get_github_api(endpoint: str, headers: Dict, org: str, repo: str) -> Tuple[bool, Optional[Dict]]:
    """调用GitHub API，返回（请求成功状态，响应数据）"""
    url = f"https://api.github.com/repos/{org}/{repo}/{endpoint}"
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == CONFIG["GITHUB_API"]["success_status_code"]:
            return True, response.json()
        elif response.status_code == CONFIG["GITHUB_API"]["not_found_status_code"]:
            return False, None
        else:
            print(f"❌ API错误（{endpoint}）：状态码 {response.status_code}", file=sys.stderr)
            print(f"    响应截断：{response.text[:CONFIG['GITHUB_API']['response_truncate_length']]}", file=sys.stderr)
            return False, None
    except Exception as e:
        print(f"❌ 请求异常（{endpoint}）：{str(e)}", file=sys.stderr)
        return False, None


def _get_item_labels(item_number: int, headers: Dict, org: str, repo: str) -> Optional[List[str]]:
    """获取指定Issue/PR的标签列表"""
    success, result = _get_github_api(f"issues/{item_number}", headers, org, repo)
    if not success or not result:
        return None
    return [label["name"] for label in result.get("labels", [])]


def run_verification(config: Dict, github_token: str, github_org: str) -> bool:
    """执行Issue/PR标签验证，返回整体结果"""
    target_repo = config[CONFIG["CONFIG_REQUIRED_FIELDS"]["target_repo"]]
    expected_labels = config[CONFIG["CONFIG_REQUIRED_FIELDS"]["expected_labels"]]
    headers = get_github_headers(github_token)
    all_passed = True

    # 打印验证起始信息
    print("=" * 60)
    print(f"📋 开始验证：{github_org}/{target_repo} 的 Issue/PR 标签分配")
    print(f"🔍 区分规则：编号 {config['issue_min']}-{config['issue_max']} 为 {CONFIG['VERIFICATION']['issue_keyword']}，其余为 {CONFIG['VERIFICATION']['pr_keyword']}")
    print("=" * 60)

    # 遍历所有待验证的Issue/PR
    for item_number, expected in expected_labels.items():
        # 区分Issue/PR类型
        item_type = CONFIG["VERIFICATION"]["issue_keyword"] if (
            config["issue_min"] <= item_number <= config["issue_max"]
        ) else CONFIG["VERIFICATION"]["pr_keyword"]
        print(f"\n1. 检查 {item_type} #{item_number}...")
        
        # 获取实际标签
        actual_labels = _get_item_labels(item_number, headers, github_org, target_repo)
        if actual_labels is None:
            print(f"   ❌ 失败：无法获取 {item_type} #{item_number} 的标签（资源不存在或权限不足）", file=sys.stderr)
            all_passed = False
            continue
        
        # 标签比对（排序后比较，忽略顺序差异）
        actual_sorted = sorted(actual_labels) if CONFIG["VERIFICATION"]["sort_labels"] else actual_labels
        expected_sorted = sorted(expected) if CONFIG["VERIFICATION"]["sort_labels"] else expected
        
        if actual_sorted == expected_sorted:
            print(f"   ✅ 成功：{item_type} #{item_number} 标签匹配 → {actual_sorted}")
        else:
            print(f"   ❌ 失败：{item_type} #{item_number} 标签不匹配", file=sys.stderr)
            print(f"      预期标签：{expected_sorted}", file=sys.stderr)
            print(f"      实际标签：{actual_sorted}", file=sys.stderr)
            all_passed = False

    # 打印最终结果
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ 所有验证检查通过！标签分配符合规范。")
    else:
        print("❌ 部分验证检查失败，请根据错误信息修正标签。", file=sys.stderr)
    print("=" * 60)

    return all_passed


def main():
    """入口函数：解析参数→加载配置→执行验证"""
    parser = argparse.ArgumentParser(description="GitHub Issue/PR标签分配合规性验证")
    parser.add_argument(
        "--config",
        type=str,
        default=DEFAULT_CONFIG_FILE,
        help=f"配置文件路径（默认：{DEFAULT_CONFIG_FILE}）"
    )
    parser.add_argument(
        "--env",
        type=str,
        default=DEFAULT_ENV_FILE,
        help=f"环境文件路径（默认：{DEFAULT_ENV_FILE}）"
    )
    args = parser.parse_args()

    # 加载环境变量与配置
    print(f"📌 加载环境变量：{args.env}")
    github_token, github_org = load_environment(args.env)

    print(f"📌 加载项目配置：{args.config}")
    project_config = load_project_config(args.config)

    # 执行验证
    print("\n" + "-" * 50)
    verification_result = run_verification(project_config, github_token, github_org)

    # 按结果退出（0=成功，1=失败）
    sys.exit(0 if verification_result else 1)


if __name__ == "__main__":
    main()
