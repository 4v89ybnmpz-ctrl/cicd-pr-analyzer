"""
GitCode PR 评论数据获取测试脚本
直接调用 GitCodePRService，不依赖 API 接口

使用方式:
  python -m app.scripts.test_gitcode_data

需要有效的 GitCode Token，配置方式:
  1. 在 config.json 的 gitcode_tokens 中设置
  2. 或设置环境变量 GITCODE_TOKEN
"""
import sys
import os
import json
import time
import logging
from typing import Dict, Any, List

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from app.services.gitcode_service import GitCodePRService, GitCodeTokenPool

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config():
    """加载配置"""
    config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config.json')
    with open(config_path, 'r') as f:
        return json.load(f)


def get_token() -> str:
    """获取 GitCode Token"""
    # 优先从环境变量获取
    token = os.environ.get('GITCODE_TOKEN', '')
    if token:
        return token

    # 从配置文件获取
    config = load_config()
    tokens = config.get('gitcode_tokens', [])
    if tokens:
        return tokens[0]

    return ''


def test_token(service: GitCodePRService) -> bool:
    """测试 Token 有效性"""
    headers = service._get_headers()
    import requests
    r = requests.get(f"{service.base_url}/user", headers=headers, timeout=10)

    if r.status_code == 200:
        user = r.json()
        logger.info(f"Token 有效，用户: {user.get('username')} (id={user.get('id')})")
        return True
    else:
        logger.error(f"Token 无效: {r.status_code} - {r.text[:200]}")
        return False


def find_projects_with_mrs(service: GitCodePRService, keywords: List[str]) -> List[Dict]:
    """搜索有 MR 的项目"""
    import requests

    headers = service._get_headers()
    found = []

    for keyword in keywords:
        logger.info(f"搜索项目: {keyword}")
        r = requests.get(
            f"{service.base_url}/projects",
            params={"search": keyword, "per_page": 10, "simple": True, "order_by": "updated"},
            headers=headers,
            timeout=15
        )

        if r.status_code != 200:
            logger.warning(f"搜索失败: {r.status_code}")
            continue

        for project in r.json():
            pid = project["id"]
            ns = project["path_with_namespace"]

            # 检查 MR 数量
            mr_r = requests.get(
                f"{service.base_url}/projects/{pid}/merge_requests",
                params={"per_page": 1, "state": "all"},
                headers=headers,
                timeout=10
            )

            total = int(mr_r.headers.get("X-Total", 0)) if mr_r.status_code == 200 else 0
            if total > 0:
                logger.info(f"  找到: {ns} (id={pid}, MR数={total})")
                found.append({
                    "id": pid,
                    "path": ns,
                    "mr_count": total,
                })

            time.sleep(0.3)

    return found


def test_fetch_mr_list(service: GitCodePRService, owner: str, repo: str) -> Dict:
    """测试获取 MR 列表"""
    logger.info(f"\n{'='*60}")
    logger.info(f"📥 获取 MR 列表: {owner}/{repo}")
    logger.info(f"{'='*60}")

    result = service.fetch_merge_requests(owner, repo, state="all", page=1, per_page=10)

    if result.get("error"):
        logger.error(f"获取失败: {result['error']}")
        return result

    mrs = result.get("merge_requests", [])
    logger.info(f"MR 总数: {result.get('total_count', len(mrs))}")

    for mr in mrs[:5]:
        author = mr.get("author", {})
        logger.info(
            f"  !{mr['iid']}: {mr['title'][:50]} "
            f"[{mr['state']}] by {author.get('username', '?')} "
            f"(评论:{mr.get('user_notes_count', 0)})"
        )

    return result


def test_fetch_mr_comments(service: GitCodePRService, owner: str, repo: str, mr_iid: int) -> Dict:
    """测试获取 MR 评论"""
    logger.info(f"\n{'='*60}")
    logger.info(f"💬 获取 MR 评论: {owner}/{repo} !{mr_iid}")
    logger.info(f"{'='*60}")

    result = service.fetch_mr_comments(owner, repo, mr_iid)

    if result.get("error"):
        logger.error(f"获取失败: {result['error']}")
        return result

    comments = result.get("comments", [])
    logger.info(f"评论总数: {len(comments)}")

    bot_count = 0
    for c in comments:
        is_bot = c.get("is_bot", False)
        if is_bot:
            bot_count += 1
        tag = " [BOT]" if is_bot else ""
        logger.info(f"  {c.get('user', '?')}{tag}: {c.get('body', '')[:80]}")

    logger.info(f"Bot 评论: {bot_count}, 用户评论: {len(comments) - bot_count}")

    return result


def test_fetch_mr_detail(service: GitCodePRService, owner: str, repo: str, mr_iid: int) -> Dict:
    """测试获取 MR 详情"""
    logger.info(f"\n{'='*60}")
    logger.info(f"📋 获取 MR 详情: {owner}/{repo} !{mr_iid}")
    logger.info(f"{'='*60}")

    result = service.fetch_mr_detail(owner, repo, mr_iid)

    if result.get("error"):
        logger.error(f"获取失败: {result['error']}")
        return result

    detail = result.get("detail", {})
    logger.info(f"标题: {detail.get('title')}")
    logger.info(f"状态: {detail.get('state')}")
    logger.info(f"分支: {detail.get('source_branch')} -> {detail.get('target_branch')}")
    logger.info(f"Pipeline: {detail.get('pipeline_status')}")
    logger.info(f"评论数: {detail.get('user_notes_count')}")
    logger.info(f"标签: {detail.get('labels')}")

    return result


def main():
    """主函数"""
    logger.info("GitCode PR 数据获取测试")
    logger.info("=" * 60)

    # 获取 Token
    token = get_token()
    if not token:
        logger.error("未配置 GitCode Token！")
        logger.info("请设置环境变量 GITCODE_TOKEN 或在 config.json 中配置 gitcode_tokens")
        return

    # 初始化服务
    token_pool = GitCodeTokenPool([token])
    config = load_config()
    settings = config.get("gitcode_settings", {
        "base_url": "https://gitcode.net/api/v4",
        "per_page": 100,
        "state": "all",
        "request_delay": 0.5,
        "max_workers": 3,
    })

    service = GitCodePRService(token_pool, settings)

    # 1. 测试 Token
    logger.info("\n🔑 测试 Token")
    if not test_token(service):
        logger.error("Token 无效，请更新后重试")
        return

    # 2. 搜索有 MR 的项目
    logger.info("\n🔍 搜索有 MR 的项目")
    projects = find_projects_with_mrs(service, ["cann", "openeuler", "mindspore"])

    if not projects:
        logger.warning("未找到有 MR 的公开项目")
        logger.info("尝试直接访问已知项目...")

        # 尝试已知项目
        test_projects = [
            ("cann", "ge"),
            ("openeuler", "kernel"),
            ("mindspore", "mindspore"),
        ]
        for owner, repo in test_projects:
            result = test_fetch_mr_list(service, owner, repo)
            if result.get("merge_requests"):
                projects.append({
                    "id": None,
                    "path": f"{owner}/{repo}",
                    "mr_count": result.get("total_count", 0),
                })

    if not projects:
        logger.error("没有可测试的项目")
        return

    # 3. 对第一个有 MR 的项目进行详细测试
    target = projects[0]
    parts = target["path"].split("/")
    owner, repo = parts[0], parts[1]

    logger.info(f"\n📊 详细测试项目: {owner}/{repo}")

    # 获取 MR 列表
    mr_result = test_fetch_mr_list(service, owner, repo)
    mrs = mr_result.get("merge_requests", [])

    if not mrs:
        logger.warning("该项目无公开 MR")
        return

    # 取第一个有评论的 MR 测试
    target_mr = None
    for mr in mrs:
        if mr.get("user_notes_count", 0) > 0:
            target_mr = mr
            break

    if not target_mr:
        target_mr = mrs[0]

    mr_iid = target_mr["iid"]

    # 获取评论
    test_fetch_mr_comments(service, owner, repo, mr_iid)

    # 获取详情
    test_fetch_mr_detail(service, owner, repo, mr_iid)

    # 汇总
    logger.info(f"\n{'='*60}")
    logger.info("📊 测试汇总")
    logger.info(f"{'='*60}")
    logger.info(f"找到项目数: {len(projects)}")
    for p in projects:
        logger.info(f"  {p['path']}: {p['mr_count']} MR")


if __name__ == "__main__":
    main()
