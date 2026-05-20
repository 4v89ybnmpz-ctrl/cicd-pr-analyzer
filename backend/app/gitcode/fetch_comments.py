"""
GitCode/AtomGit PR 评论获取脚本

使用方式:
  python -m app.gitcode.fetch_comments cann ge --limit 10

  或指定 Token:
  GITCODE_TOKEN=xxx python -m app.gitcode.fetch_comments cann ge --limit 10
"""
import sys
import os
import json
import argparse
import logging
import asyncio
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from app.gitcode.service import AtomGitService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_token() -> str:
    """从配置文件或环境变量加载 Token"""
    token = os.environ.get('GITCODE_TOKEN', '')
    if token:
        return token

    config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config.json')
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
        tokens = config.get('gitcode_tokens', [])
        if tokens:
            return tokens[0]

    return ''


async def _run(args):
    """异步主逻辑"""
    token = args.token or load_token()
    if not token:
        logger.error("未配置 Token！设置环境变量 GITCODE_TOKEN 或使用 --token 参数")
        sys.exit(1)

    # 初始化服务
    service = AtomGitService(access_token=token)

    try:
        # 验证 Token
        logger.info("验证 Token")
        user = await service.get_user()
        if not user:
            logger.error("Token 无效")
            sys.exit(1)
        logger.info(f"用户: {user.get('login')} (id={user.get('id')})")

        # 获取 PR 及评论
        start_time = time.time()
        logger.info(f"\n获取 {args.owner}/{args.repo} PR 评论 (limit={args.limit})")

        result = await service.fetch_pulls_with_comments(
            args.owner, args.repo,
            limit=args.limit, state=args.state
        )

        if result.get("error"):
            logger.error(f"获取失败: {result['error']}")
            sys.exit(1)

        # 输出结果
        elapsed = time.time() - start_time
        logger.info(f"\n{'='*60}")
        logger.info("获取结果汇总")
        logger.info(f"{'='*60}")
        logger.info(f"项目: {args.owner}/{args.repo}")
        logger.info(f"PR 数: {result['total_prs']}")
        logger.info(f"总评论: {result['total_comments']}")
        logger.info(f"Bot 评论: {result['bot_comments']}")
        logger.info(f"耗时: {elapsed:.1f}s")

        # 展示各 PR 评论详情
        for pr in result.get("results", []):
            logger.info(f"\n  PR#{pr['pull_number']}: {pr['title'][:50]} [{pr['state']}]")
            logger.info(f"  评论: {pr['comment_count']} (Bot: {pr['bot_comment_count']})")

            for c in pr.get("comments", []):
                tag = " [BOT]" if c.get("is_bot") else ""
                logger.info(f"    {c['user']}{tag}: {c.get('body', '')[:80]}")

                # 展示提取的流水线信息
                if c.get("pipeline_info"):
                    pi = c["pipeline_info"]
                    logger.info(f"    -> 流水线: {pi.get('pipeline_id', '?')[:12]} run={pi.get('pipeline_run_id', '?')[:12]}")
                    for task in pi.get("tasks", []):
                        logger.info(f"    -> 任务: {task['name']} [{task['status']}]")

        # 保存到文件
        if args.save:
            output_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'gitcode')
            os.makedirs(output_dir, exist_ok=True)
            filename = f"{args.owner}_{args.repo}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join(output_dir, filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            logger.info(f"\n结果已保存: {filepath}")
    finally:
        await service.close()


def main():
    parser = argparse.ArgumentParser(description='GitCode/AtomGit PR 评论获取')
    parser.add_argument('owner', help='仓库所有者')
    parser.add_argument('repo', help='仓库名')
    parser.add_argument('--limit', type=int, default=10, help='获取 PR 数量 (默认 10)')
    parser.add_argument('--state', default='all', help='PR 状态: open/closed/all (默认 all)')
    parser.add_argument('--token', default=None, help='AtomGit Token')
    parser.add_argument('--save', action='store_true', help='保存结果到 JSON 文件')
    args = parser.parse_args()

    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
