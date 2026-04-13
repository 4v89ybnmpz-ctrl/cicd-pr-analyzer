"""
下载 rust-lang/rust 最新 500 个 PR 及其评论
直接调用 GitHub API + 数据库服务，绕过全量分页限制
"""
import sys
import os
import time
import json
import requests
from datetime import datetime

# 添加 backend 到路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from app.services.database_service import DatabaseService
from app.core.encryption import get_password_manager

# GitHub 配置
OWNER = "rust-lang"
REPO = "rust"
TARGET_PR_COUNT = 500
GITHUB_BASE_URL = "https://api.github.com"
PER_PAGE = 100  # GitHub API 单页最大值

# 从配置文件加载 Token
with open(os.path.join(os.path.dirname(__file__), '..', '..', 'config.json'), 'r') as f:
    config = json.load(f)
TOKENS = config.get('tokens', [])
token_index = 0


def get_token():
    """轮询获取 Token"""
    global token_index
    if not TOKENS:
        return None
    token = TOKENS[token_index % len(TOKENS)]
    token_index += 1
    return token


def github_request(url, params=None, timeout=30):
    """发起 GitHub API 请求"""
    token = get_token()
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "GitHub-PR-Fetcher"
    }
    if token:
        headers["Authorization"] = f"token {token}"

    for attempt in range(3):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 403:
                # 速率限制
                reset_time = int(resp.headers.get('X-RateLimit-Reset', 0))
                wait_time = max(reset_time - int(time.time()), 0) + 1
                print(f"  ⚠️ 速率限制，等待 {wait_time}s...")
                time.sleep(min(wait_time, 60))
                continue
            else:
                print(f"  ❌ 请求失败: {resp.status_code}")
                return None
        except Exception as e:
            print(f"  ⚠️ 请求异常 (尝试 {attempt+1}/3): {e}")
            time.sleep(2)
    return None


def fetch_latest_prs(owner, repo, count):
    """获取最新的 N 个 PR"""
    print(f"\n{'='*60}")
    print(f"📥 获取 {owner}/{repo} 最新 {count} 个 PR")
    print(f"{'='*60}")

    all_prs = []
    page = 1

    while len(all_prs) < count:
        print(f"  获取第 {page} 页... (已获取 {len(all_prs)}/{count})")

        url = f"{GITHUB_BASE_URL}/repos/{owner}/{repo}/pulls"
        params = {
            "state": "all",
            "sort": "updated",
            "direction": "desc",
            "per_page": PER_PAGE,
            "page": page
        }

        prs = github_request(url, params)
        if not prs:
            break

        for pr in prs:
            all_prs.append({
                "number": pr.get("number"),
                "title": pr.get("title"),
                "user": pr.get("user", {}).get("login"),
                "state": pr.get("state"),
                "created_at": pr.get("created_at"),
                "updated_at": pr.get("updated_at"),
                "url": pr.get("html_url")
            })

        if len(prs) < PER_PAGE:
            break

        page += 1
        time.sleep(0.5)

    # 截取目标数量
    all_prs = all_prs[:count]
    print(f"  ✅ 共获取 {len(all_prs)} 个 PR")
    return all_prs


def fetch_pr_comments(owner, repo, pr_number):
    """获取指定 PR 的所有评论"""
    all_comments = []
    page = 1

    while True:
        url = f"{GITHUB_BASE_URL}/repos/{owner}/{repo}/issues/{pr_number}/comments"
        params = {"per_page": PER_PAGE, "page": page}

        comments = github_request(url, params)
        if not comments:
            break

        for comment in comments:
            user = comment.get("user", {})
            user_login = user.get("login", "")
            user_type = user.get("type", "User")

            # 识别 Bot
            is_bot = (
                user_type == "Bot" or
                user_login.endswith('[bot]') or
                user_login.endswith('-bot') or
                'bot' in user_login.lower()
            )

            all_comments.append({
                "id": comment.get("id"),
                "user": user_login,
                "user_id": user.get("id"),
                "user_type": user_type,
                "avatar_url": user.get("avatar_url"),
                "is_bot": is_bot,
                "author_association": comment.get("author_association"),
                "body": comment.get("body"),
                "created_at": comment.get("created_at"),
                "updated_at": comment.get("updated_at"),
                "url": comment.get("html_url"),
                "reactions": comment.get("reactions", {}).get("total_count", 0) if comment.get("reactions") else 0
            })

        if len(comments) < PER_PAGE:
            break

        page += 1
        time.sleep(0.3)

    return all_comments


def main():
    """主函数"""
    start_time = time.time()

    # 1. 获取最新 500 个 PR
    prs = fetch_latest_prs(OWNER, REPO, TARGET_PR_COUNT)
    if not prs:
        print("❌ 获取 PR 列表失败")
        return

    # 2. 连接数据库
    print(f"\n{'='*60}")
    print(f"💾 连接数据库")
    print(f"{'='*60}")

    db = DatabaseService()
    if not db.connect():
        print("❌ 数据库连接失败")
        return
    print("✅ 数据库连接成功")

    # 3. 保存 PR 列表数据
    pr_data = {
        "owner": OWNER,
        "repo": REPO,
        "prs": prs,
        "total": len(prs)
    }
    if db.save_pr_data(OWNER, REPO, pr_data):
        print(f"✅ PR 列表已保存到数据库 ({len(prs)} 个)")
    else:
        print("⚠️ PR 列表保存失败")

    # 4. 逐个获取评论并保存
    print(f"\n{'='*60}")
    print(f"💬 开始获取 PR 评论 (共 {len(prs)} 个 PR)")
    print(f"{'='*60}")

    success_count = 0
    fail_count = 0
    skip_count = 0
    total_comments = 0

    for i, pr in enumerate(prs, 1):
        pr_number = pr["number"]

        # 检查数据库中是否已有该 PR 的评论
        existing = db.get_pr_comments(OWNER, REPO, pr_number)
        if existing and existing.get("data", {}).get("comments"):
            skip_count += 1
            existing_count = len(existing["data"]["comments"])
            total_comments += existing_count
            if i % 50 == 0 or i == len(prs):
                print(f"  [{i}/{len(prs)}] PR#{pr_number} 已存在 ({existing_count} 条评论)，跳过")
            continue

        # 获取评论
        comments = fetch_pr_comments(OWNER, REPO, pr_number)

        # 保存到数据库
        comments_data = {
            "owner": OWNER,
            "repo": REPO,
            "pr_number": pr_number,
            "comments": comments,
            "total": len(comments)
        }

        if db.save_pr_comments(OWNER, REPO, pr_number, comments_data):
            success_count += 1
            total_comments += len(comments)
        else:
            fail_count += 1

        # 进度显示
        if i % 10 == 0 or i == len(prs):
            elapsed = time.time() - start_time
            rate = i / elapsed if elapsed > 0 else 0
            eta = (len(prs) - i) / rate if rate > 0 else 0
            print(f"  [{i}/{len(prs)}] PR#{pr_number} - {len(comments)} 条评论 | "
                  f"成功:{success_count} 跳过:{skip_count} 失败:{fail_count} | "
                  f"总评论:{total_comments} | ETA: {eta/60:.1f}min")

        time.sleep(0.5)  # 控制请求频率

    # 5. 汇总
    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"📊 下载汇总")
    print(f"{'='*60}")
    print(f"项目: {OWNER}/{REPO}")
    print(f"PR 数量: {len(prs)}")
    print(f"评论获取: 成功 {success_count}, 跳过 {skip_count}, 失败 {fail_count}")
    print(f"总评论数: {total_comments}")
    print(f"耗时: {elapsed/60:.1f} 分钟")

    # 统计 Bot 评论
    db_stats = db.get_stats()
    print(f"\n数据库统计: {json.dumps(db_stats, indent=2, ensure_ascii=False)}")

    db.disconnect()


if __name__ == "__main__":
    main()
