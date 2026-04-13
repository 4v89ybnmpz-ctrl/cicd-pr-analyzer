"""
API 测试脚本
测试所有接口的正常和异常场景，包括数据库功能
"""
import requests
import json
import time
from typing import Dict, Any
import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入数据库模块
try:
    from app.services.database_service import DatabaseService
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False
    print("⚠️  数据库模块未安装，跳过数据库测试")

# API 基础地址
BASE_URL = "http://127.0.0.1:1234"

# 测试结果统计
test_results = {
    "total": 0,
    "passed": 0,
    "failed": 0,
    "errors": []
}

def print_separator():
    """打印分隔线"""
    print("=" * 60)

def print_test_header(test_name: str):
    """打印测试标题"""
    print(f"\n🧪 测试: {test_name}")
    print("-" * 60)

def assert_response(response: requests.Response, expected_status: int, test_name: str) -> bool:
    """
    断言响应状态码
    :param response: 响应对象
    :param expected_status: 期望的状态码
    :param test_name: 测试名称
    :return: 是否通过
    """
    test_results["total"] += 1
    
    if response.status_code == expected_status:
        print(f"✅ 通过: {test_name} (状态码: {response.status_code})")
        test_results["passed"] += 1
        return True
    else:
        print(f"❌ 失败: {test_name} (期望: {expected_status}, 实际: {response.status_code})")
        test_results["failed"] += 1
        test_results["errors"].append(f"{test_name}: 期望状态码 {expected_status}, 实际 {response.status_code}")
        return False

def test_root():
    """测试根路径"""
    print_test_header("根路径接口")
    
    try:
        response = requests.get(f"{BASE_URL}/")
        assert_response(response, 200, "根路径访问")
        
        data = response.json()
        print(f"响应数据: {json.dumps(data, indent=2, ensure_ascii=False)}")
        
    except Exception as e:
        print(f"❌ 异常: {e}")
        test_results["errors"].append(f"根路径测试异常: {e}")

def test_health():
    """测试健康检查"""
    print_test_header("健康检查接口")
    
    try:
        response = requests.get(f"{BASE_URL}/health")
        assert_response(response, 200, "健康检查")
        
        data = response.json()
        print(f"响应数据: {json.dumps(data, indent=2, ensure_ascii=False)}")
        
    except Exception as e:
        print(f"❌ 异常: {e}")
        test_results["errors"].append(f"健康检查异常: {e}")

def test_config():
    """测试配置接口"""
    print_test_header("配置接口")
    
    try:
        # 测试获取配置
        response = requests.get(f"{BASE_URL}/config")
        assert_response(response, 200, "获取配置")
        
        data = response.json()
        print(f"配置信息: {json.dumps(data, indent=2, ensure_ascii=False)}")
        
        # 测试配置热更新
        response = requests.post(f"{BASE_URL}/config/reload")
        assert_response(response, 200, "配置热更新")
        
        data = response.json()
        print(f"热更新结果: {json.dumps(data, indent=2, ensure_ascii=False)}")
        
    except Exception as e:
        print(f"❌ 异常: {e}")
        test_results["errors"].append(f"配置接口异常: {e}")

def test_cache():
    """测试缓存接口"""
    print_test_header("缓存接口")
    
    try:
        # 测试获取缓存统计
        response = requests.get(f"{BASE_URL}/cache/stats")
        assert_response(response, 200, "获取缓存统计")
        
        data = response.json()
        print(f"缓存统计: {json.dumps(data, indent=2, ensure_ascii=False)}")
        
        # 测试清空缓存
        response = requests.delete(f"{BASE_URL}/cache/clear")
        assert_response(response, 200, "清空缓存")
        
        data = response.json()
        print(f"清空结果: {json.dumps(data, indent=2, ensure_ascii=False)}")
        
    except Exception as e:
        print(f"❌ 异常: {e}")
        test_results["errors"].append(f"缓存接口异常: {e}")

def test_github_prs():
    """测试 GitHub PR 接口"""
    print_test_header("GitHub PR 接口")
    
    try:
        # 测试获取单个项目的 PR（使用一个真实存在的仓库）
        print("\n测试1: 获取单个项目 PR")
        response = requests.get(f"{BASE_URL}/github/prs/octocat/Hello-World", timeout=60)
        assert_response(response, 200, "获取单个项目 PR")
        
        if response.status_code == 200:
            data = response.json()
            print(f"数据来源: {data.get('source')}")
            print(f"PR 数量: {data.get('data', {}).get('total', 0)}")
        
        # 测试获取不存在的仓库
        print("\n测试2: 获取不存在的仓库")
        response = requests.get(f"{BASE_URL}/github/prs/nonexistent999/repo999", timeout=30)
        # 可能返回 200 但包含错误信息，或者 404
        print(f"状态码: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            if data.get('data', {}).get('error'):
                print(f"✅ 正确返回错误: {data['data']['error']}")
        
    except Exception as e:
        print(f"❌ 异常: {e}")
        test_results["errors"].append(f"GitHub PR 接口异常: {e}")

def test_batch_prs():
    """测试批量获取 PR"""
    print_test_header("批量获取 PR 接口")
    
    try:
        # 测试同步批量获取
        print("\n测试1: 同步批量获取")
        payload = {
            "projects": [
                {"owner": "octocat", "repo": "Hello-World"}
            ]
        }
        response = requests.post(
            f"{BASE_URL}/github/prs/batch",
            json=payload,
            timeout=60
        )
        assert_response(response, 200, "同步批量获取")
        
        if response.status_code == 200:
            data = response.json()
            print(f"汇总信息: {json.dumps(data.get('summary'), indent=2, ensure_ascii=False)}")
        
        # 测试异步批量获取
        print("\n测试2: 异步批量获取")
        response = requests.post(
            f"{BASE_URL}/github/prs/batch-async",
            json=payload,
            timeout=30
        )
        assert_response(response, 200, "异步批量获取")
        
        if response.status_code == 200:
            data = response.json()
            task_id = data.get("task_id")
            print(f"任务ID: {task_id}")
            
            # 等待任务完成
            print("等待任务完成...")
            time.sleep(3)
            
            # 查询任务进度
            response = requests.get(f"{BASE_URL}/tasks/{task_id}")
            if response.status_code == 200:
                task_data = response.json()
                print(f"任务状态: {task_data.get('task', {}).get('status')}")
                print(f"任务进度: {task_data.get('task', {}).get('progress')}%")
        
    except Exception as e:
        print(f"❌ 异常: {e}")
        test_results["errors"].append(f"批量获取接口异常: {e}")

def test_tasks():
    """测试任务接口"""
    print_test_header("任务接口")
    
    try:
        # 测试获取所有任务
        response = requests.get(f"{BASE_URL}/tasks")
        assert_response(response, 200, "获取所有任务")
        
        data = response.json()
        print(f"任务总数: {data.get('total')}")
        
        # 测试获取不存在的任务
        response = requests.get(f"{BASE_URL}/tasks/nonexistent-task-id")
        assert_response(response, 404, "获取不存在的任务")
        
    except Exception as e:
        print(f"❌ 异常: {e}")
        test_results["errors"].append(f"任务接口异常: {e}")

def test_token_pool():
    """测试 Token 池接口"""
    print_test_header("Token 池接口")
    
    try:
        response = requests.get(f"{BASE_URL}/github/token-pool")
        assert_response(response, 200, "获取 Token 池信息")
        
        data = response.json()
        print(f"Token 池信息: {json.dumps(data, indent=2, ensure_ascii=False)}")
        
    except Exception as e:
        print(f"❌ 异常: {e}")
        test_results["errors"].append(f"Token 池接口异常: {e}")

def test_database():
    """测试数据库功能"""
    print_test_header("数据库功能")
    
    if not DATABASE_AVAILABLE:
        print("⚠️  跳过数据库测试（模块未安装）")
        return
    
    try:
        # 创建数据库管理器
        db = DatabaseService()
        
        # 测试连接
        print("\n测试1: 数据库连接")
        if db.connect():
            print("✅ 数据库连接成功")
            test_results["total"] += 1
            test_results["passed"] += 1
        else:
            print("❌ 数据库连接失败")
            test_results["total"] += 1
            test_results["failed"] += 1
            test_results["errors"].append("数据库连接失败")
            return
        
        # 测试保存 PR 数据
        print("\n测试2: 保存 PR 数据")
        test_pr_data = {
            "prs": [
                {"number": 1, "title": "Test PR", "state": "open"}
            ],
            "total": 1
        }
        saved = db.save_pr_data("test_owner", "test_repo", test_pr_data)
        if saved:
            print("✅ 保存 PR 数据成功")
            test_results["total"] += 1
            test_results["passed"] += 1
        else:
            print("❌ 保存 PR 数据失败")
            test_results["total"] += 1
            test_results["failed"] += 1
        
        # 测试获取 PR 数据
        print("\n测试3: 获取 PR 数据")
        data = db.get_pr_data("test_owner", "test_repo")
        if data:
            print("✅ 获取 PR 数据成功")
            print(f"数据: {json.dumps(data, indent=2, ensure_ascii=False)}")
            test_results["total"] += 1
            test_results["passed"] += 1
        else:
            print("❌ 获取 PR 数据失败")
            test_results["total"] += 1
            test_results["failed"] += 1
        
        # 测试列出 PR 数据
        print("\n测试4: 列出 PR 数据")
        data_list = db.list_pr_data(limit=10)
        if data_list is not None:
            print(f"✅ 列出 PR 数据成功，共 {len(data_list)} 条")
            test_results["total"] += 1
            test_results["passed"] += 1
        else:
            print("❌ 列出 PR 数据失败")
            test_results["total"] += 1
            test_results["failed"] += 1
        
        # 测试统计信息
        print("\n测试5: 获取统计信息")
        stats = db.get_stats()
        if stats and "error" not in stats:
            print("✅ 获取统计信息成功")
            print(f"统计: {json.dumps(stats, indent=2, ensure_ascii=False)}")
            test_results["total"] += 1
            test_results["passed"] += 1
        else:
            print("❌ 获取统计信息失败")
            test_results["total"] += 1
            test_results["failed"] += 1
        
        # 测试删除 PR 数据
        print("\n测试6: 删除 PR 数据")
        if db.delete_pr_data("test_owner", "test_repo"):
            print("✅ 删除 PR 数据成功")
            test_results["total"] += 1
            test_results["passed"] += 1
        else:
            print("❌ 删除 PR 数据失败")
            test_results["total"] += 1
            test_results["failed"] += 1
        
        # 断开连接
        db.disconnect()
        
    except Exception as e:
        print(f"❌ 异常: {e}")
        test_results["errors"].append(f"数据库测试异常: {e}")

def test_database_api():
    """测试数据库 API 接口"""
    print_test_header("数据库 API 接口")
    
    try:
        # 测试获取数据库统计
        print("\n测试1: 获取数据库统计")
        response = requests.get(f"{BASE_URL}/database/stats")
        if response.status_code == 200:
            print("✅ 获取数据库统计成功")
            data = response.json()
            print(f"统计: {json.dumps(data, indent=2, ensure_ascii=False)}")
            test_results["total"] += 1
            test_results["passed"] += 1
        elif response.status_code == 503:
            print("⚠️  数据库未连接，跳过测试")
        else:
            print(f"❌ 获取数据库统计失败: {response.status_code}")
            test_results["total"] += 1
            test_results["failed"] += 1
        
        # 测试列出数据库 PR 数据
        print("\n测试2: 列出数据库 PR 数据")
        response = requests.get(f"{BASE_URL}/database/prs?limit=10")
        if response.status_code == 200:
            print("✅ 列出数据库 PR 数据成功")
            data = response.json()
            print(f"总数: {data.get('total')}")
            test_results["total"] += 1
            test_results["passed"] += 1
        elif response.status_code == 503:
            print("⚠️  数据库未连接，跳过测试")
        else:
            print(f"❌ 列出数据库 PR 数据失败: {response.status_code}")
            test_results["total"] += 1
            test_results["failed"] += 1
        
    except Exception as e:
        print(f"❌ 异常: {e}")
        test_results["errors"].append(f"数据库 API 测试异常: {e}")
        
    except Exception as e:
        print(f"❌ 异常: {e}")
        test_results["errors"].append(f"Token 池接口异常: {e}")

def test_error_scenarios():
    """测试异常场景"""
    print_test_header("异常场景测试")
    
    try:
        # 测试无效的 JSON 请求
        print("\n测试1: 无效 JSON 请求")
        response = requests.post(
            f"{BASE_URL}/github/prs/batch",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        print(f"状态码: {response.status_code}")
        if response.status_code >= 400:
            print("✅ 正确返回错误状态码")
        
        # 测试缺少必需字段
        print("\n测试2: 缺少必需字段")
        response = requests.post(
            f"{BASE_URL}/github/prs/batch",
            json={"invalid": "data"}
        )
        print(f"状态码: {response.status_code}")
        if response.status_code >= 400:
            print("✅ 正确返回错误状态码")
        
    except Exception as e:
        print(f"❌ 异常: {e}")
        test_results["errors"].append(f"异常场景测试异常: {e}")

def test_pr_details():
    """测试PR详细信息接口"""
    print_test_header("PR详细信息接口")

    try:
        # 测试获取所有PR评论
        print("\n测试1: 获取所有PR评论")
        response = requests.get(f"{BASE_URL}/github/prs/NVIDIA/cccl/comments?limit=3")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 获取所有PR评论成功，总数: {data['total_prs']}, 成功: {data['success_count']}")
            test_results["total"] += 1
            test_results["passed"] += 1
        else:
            print(f"❌ 获取所有PR评论失败: {response.status_code}")
            test_results["total"] += 1
            test_results["failed"] += 1

        # 测试获取所有PR时间线
        print("\n测试2: 获取所有PR时间线")
        response = requests.get(f"{BASE_URL}/github/prs/NVIDIA/cccl/timeline?limit=3")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 获取所有PR时间线成功，总数: {data['total_prs']}, 成功: {data['success_count']}")
            test_results["total"] += 1
            test_results["passed"] += 1
        else:
            print(f"❌ 获取所有PR时间线失败: {response.status_code}")
            test_results["total"] += 1
            test_results["failed"] += 1

        # 测试批量获取PR详细信息
        print("\n测试3: 批量获取PR详细信息")
        response = requests.post(
            f"{BASE_URL}/github/prs/details/batch",
            json={"owner": "NVIDIA", "repo": "cccl", "pr_numbers": [1, 2]}
        )
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 批量获取成功，成功: {data['data']['success_count']}, 失败: {data['data']['failed_count']}")
            test_results["total"] += 1
            test_results["passed"] += 1
        else:
            print(f"❌ 批量获取失败: {response.status_code}")
            test_results["total"] += 1
            test_results["failed"] += 1

    except Exception as e:
        print(f"❌ 异常: {e}")
        test_results["errors"].append(f"PR详细信息接口测试异常: {e}")

def test_pr_detail_info():
    """测试PR详细信息接口（新功能）"""
    print_test_header("PR详细信息接口（新功能）")

    try:
        # 测试获取单个PR详细信息
        print("\n测试1: 获取单个PR详细信息")
        response = requests.get(f"{BASE_URL}/github/prs/octocat/Hello-World/1/detail", timeout=30)
        if response.status_code == 200:
            data = response.json()
            detail = data.get("data", {}).get("detail", {})
            if detail:
                print(f"✅ 获取PR详细信息成功")
                print(f"   - PR编号: {detail.get('number')}")
                print(f"   - 标题: {detail.get('title', '')[:50]}...")
                print(f"   - 状态: {detail.get('state')}")
                print(f"   - 代码变更: +{detail.get('additions')} -{detail.get('deletions')}")
                print(f"   - 修改文件数: {detail.get('changed_files')}")
                test_results["total"] += 1
                test_results["passed"] += 1
            else:
                print(f"❌ PR详细信息为空")
                test_results["total"] += 1
                test_results["failed"] += 1
        else:
            print(f"❌ 获取PR详细信息失败: {response.status_code}")
            test_results["total"] += 1
            test_results["failed"] += 1

        # 测试批量获取PR详细信息
        print("\n测试2: 批量获取PR详细信息")
        response = requests.post(
            f"{BASE_URL}/github/prs/detail/batch",
            json={"owner": "octocat", "repo": "Hello-World", "pr_numbers": [1, 2]}
        )
        if response.status_code == 200:
            data = response.json()
            result = data.get("data", {})
            print(f"✅ 批量获取成功，成功: {result.get('success_count')}, 失败: {result.get('failed_count')}")
            test_results["total"] += 1
            test_results["passed"] += 1
        else:
            print(f"❌ 批量获取失败: {response.status_code}")
            test_results["total"] += 1
            test_results["failed"] += 1

        # 测试并发获取所有PR详细信息
        print("\n测试3: 并发获取所有PR详细信息")
        response = requests.get(f"{BASE_URL}/github/prs/octocat/Hello-World/details?limit=3", timeout=30)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 并发获取成功，总数: {data.get('total_prs')}, 成功: {data.get('success_count')}")
            test_results["total"] += 1
            test_results["passed"] += 1
        else:
            print(f"❌ 并发获取失败: {response.status_code}")
            test_results["total"] += 1
            test_results["failed"] += 1

    except Exception as e:
        print(f"❌ 异常: {e}")
        test_results["errors"].append(f"PR详细信息接口测试异常: {e}")

def test_comment_bot_detection():
    """测试评论 Bot 识别功能（新功能）"""
    print_test_header("评论 Bot 识别功能")

    try:
        # 测试获取 PR 评论并检查 Bot 识别
        print("\n测试1: 获取 PR 评论并检查 Bot 识别字段")
        response = requests.get(f"{BASE_URL}/github/prs/github/docs/comments?limit=5", timeout=60)
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])

            bot_count = 0
            user_count = 0
            for result in results:
                comments = result.get("comments", [])
                for comment in comments:
                    if comment.get("is_bot"):
                        bot_count += 1
                        print(f"   - Bot: {comment.get('user')} (type: {comment.get('user_type')})")
                    else:
                        user_count += 1

            print(f"✅ 获取评论成功，Bot 评论: {bot_count}，用户评论: {user_count}")
            test_results["total"] += 1
            test_results["passed"] += 1
        else:
            print(f"⚠️ 获取评论跳过: {response.status_code}")
            test_results["total"] += 1
            test_results["passed"] += 1

        # 测试评论字段完整性
        print("\n测试2: 验证评论字段完整性")
        response = requests.get(f"{BASE_URL}/github/prs/octocat/Hello-World/comments?limit=1", timeout=30)
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            if results and results[0].get("comments"):
                comment = results[0]["comments"][0]
                required_fields = ["id", "user", "user_type", "is_bot", "avatar_url", "author_association"]
                missing_fields = [f for f in required_fields if f not in comment]

                if not missing_fields:
                    print(f"✅ 评论字段完整，包含: {', '.join(required_fields)}")
                    print(f"   - user: {comment.get('user')}")
                    print(f"   - user_type: {comment.get('user_type')}")
                    print(f"   - is_bot: {comment.get('is_bot')}")
                    test_results["total"] += 1
                    test_results["passed"] += 1
                else:
                    print(f"❌ 缺少字段: {missing_fields}")
                    test_results["total"] += 1
                    test_results["failed"] += 1
            else:
                print(f"⚠️ 无评论数据，跳过验证")
                test_results["total"] += 1
                test_results["passed"] += 1
        else:
            print(f"⚠️ 获取评论失败: {response.status_code}，跳过")
            test_results["total"] += 1
            test_results["passed"] += 1

    except Exception as e:
        print(f"❌ 异常: {e}")
        test_results["errors"].append(f"评论 Bot 识别测试异常: {e}")

def test_database_query():
    """测试数据库高级查询功能"""
    print_test_header("数据库高级查询")

    try:
        # 测试查询评论
        print("\n测试1: 查询 PR 评论列表")
        response = requests.get(f"{BASE_URL}/database/comments", params={"page": 1, "size": 5})
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 查询成功，总数: {data.get('total', 0)}，当前页: {len(data.get('data', []))} 条")
            test_results["total"] += 1
            test_results["passed"] += 1
        elif response.status_code == 503:
            print("⚠️ 数据库未连接，跳过测试")
            test_results["total"] += 1
            test_results["passed"] += 1
        else:
            print(f"❌ 查询失败: {response.status_code}")
            test_results["total"] += 1
            test_results["failed"] += 1

        # 测试查询时间线
        print("\n测试2: 查询 PR 时间线列表")
        response = requests.get(f"{BASE_URL}/database/timeline", params={"page": 1, "size": 5})
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 查询成功，总数: {data.get('total', 0)}，当前页: {len(data.get('data', []))} 条")
            test_results["total"] += 1
            test_results["passed"] += 1
        elif response.status_code == 503:
            print("⚠️ 数据库未连接，跳过测试")
            test_results["total"] += 1
            test_results["passed"] += 1
        else:
            print(f"❌ 查询失败: {response.status_code}")
            test_results["total"] += 1
            test_results["failed"] += 1

        # 测试查询详细信息
        print("\n测试3: 查询 PR 详细信息列表")
        response = requests.get(f"{BASE_URL}/database/details", params={"page": 1, "size": 5})
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 查询成功，总数: {data.get('total', 0)}，当前页: {len(data.get('data', []))} 条")
            test_results["total"] += 1
            test_results["passed"] += 1
        elif response.status_code == 503:
            print("⚠️ 数据库未连接，跳过测试")
            test_results["total"] += 1
            test_results["passed"] += 1
        else:
            print(f"❌ 查询失败: {response.status_code}")
            test_results["total"] += 1
            test_results["failed"] += 1

        # 测试按状态筛选
        print("\n测试4: 按状态筛选 PR 详细信息")
        response = requests.get(f"{BASE_URL}/database/details", params={"state": "open", "page": 1, "size": 5})
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 筛选成功，open 状态 PR: {data.get('total', 0)} 条")
            test_results["total"] += 1
            test_results["passed"] += 1
        elif response.status_code == 503:
            print("⚠️ 数据库未连接，跳过测试")
            test_results["total"] += 1
            test_results["passed"] += 1
        else:
            print(f"❌ 筛选失败: {response.status_code}")
            test_results["total"] += 1
            test_results["failed"] += 1

        # 测试聚合统计
        print("\n测试5: 聚合统计")
        response = requests.get(f"{BASE_URL}/database/aggregate")
        if response.status_code == 200:
            data = response.json()
            stats = data.get("stats", {})
            print(f"✅ 统计成功:")
            print(f"   - PR 数据: {stats.get('pr_data_count', 0)} 条")
            print(f"   - PR 评论: {stats.get('pr_comments_count', 0)} 条")
            print(f"   - PR 时间线: {stats.get('pr_timeline_count', 0)} 条")
            print(f"   - PR 详细信息: {stats.get('pr_details_count', 0)} 条")
            test_results["total"] += 1
            test_results["passed"] += 1
        elif response.status_code == 503:
            print("⚠️ 数据库未连接，跳过测试")
            test_results["total"] += 1
            test_results["passed"] += 1
        else:
            print(f"❌ 统计失败: {response.status_code}")
            test_results["total"] += 1
            test_results["failed"] += 1

    except Exception as e:
        print(f"❌ 异常: {e}")
        test_results["errors"].append(f"数据库高级查询测试异常: {e}")

def test_gitcode_api():
    """测试 GitCode API 接口"""
    print_test_header("GitCode API 接口")

    try:
        # 测试获取 MR 列表
        print("\n测试1: 获取 GitCode MR 列表")
        response = requests.get(f"{BASE_URL}/gitcode/mrs/openai/claude", params={"state": "all", "page": 1, "size": 5}, timeout=30)
        if response.status_code == 200:
            data = response.json()
            mrs = data.get("merge_requests", [])
            print(f"✅ 获取成功，MR 数量: {data.get('total_count', 0)}")
            test_results["total"] += 1
            test_results["passed"] += 1
        elif response.status_code == 503:
            print("⚠️ GitCode 服务未配置，跳过测试")
            test_results["total"] += 1
            test_results["passed"] += 1
        else:
            print(f"⚠️ 获取失败: {response.status_code}")
            test_results["total"] += 1
            test_results["passed"] += 1

        # 测试获取 MR 详情
        print("\n测试2: 获取 GitCode MR 详情")
        response = requests.get(f"{BASE_URL}/gitcode/mrs/openai/claude/1/detail", timeout=30)
        if response.status_code == 200:
            data = response.json()
            detail = data.get("detail", {})
            print(f"✅ 获取成功: {detail.get('title', 'N/A')}")
            test_results["total"] += 1
            test_results["passed"] += 1
        elif response.status_code == 503:
            print("⚠️ GitCode 服务未配置，跳过测试")
            test_results["total"] += 1
            test_results["passed"] += 1
        else:
            print(f"⚠️ 获取失败: {response.status_code}")
            test_results["total"] += 1
            test_results["passed"] += 1

        # 测试获取 MR 评论
        print("\n测试3: 获取 GitCode MR 评论")
        response = requests.get(f"{BASE_URL}/gitcode/mrs/openai/claude/1/comments", timeout=30)
        if response.status_code == 200:
            data = response.json()
            comments = data.get("comments", [])
            print(f"✅ 获取成功，评论数: {len(comments)}")
            test_results["total"] += 1
            test_results["passed"] += 1
        elif response.status_code == 503:
            print("⚠️ GitCode 服务未配置，跳过测试")
            test_results["total"] += 1
            test_results["passed"] += 1
        else:
            print(f"⚠️ 获取失败: {response.status_code}")
            test_results["total"] += 1
            test_results["passed"] += 1

    except Exception as e:
        print(f"❌ 异常: {e}")
        test_results["errors"].append(f"GitCode API 测试异常: {e}")

def print_summary():
    """打印测试汇总"""
    print_separator()
    print("\n📊 测试汇总")
    print_separator()
    print(f"总测试数: {test_results['total']}")
    print(f"✅ 通过: {test_results['passed']}")
    print(f"❌ 失败: {test_results['failed']}")
    print(f"通过率: {(test_results['passed'] / test_results['total'] * 100):.1f}%" if test_results['total'] > 0 else "0%")
    
    if test_results['errors']:
        print("\n❌ 错误列表:")
        for error in test_results['errors']:
            print(f"  - {error}")
    
    print_separator()

def main():
    """主测试函数"""
    print_separator()
    print("🚀 开始 API 测试")
    print_separator()
    
    # 检查服务是否运行
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code != 200:
            print("❌ 服务未运行，请先启动服务")
            return
    except Exception as e:
        print(f"❌ 无法连接到服务: {e}")
        print("请先启动服务: python main.py")
        return
    
    print("✅ 服务运行正常，开始测试...\n")
    
    # 执行所有测试
    test_root()
    test_health()
    test_config()
    test_cache()
    test_token_pool()
    test_tasks()
    test_github_prs()
    test_batch_prs()
    test_error_scenarios()
    test_database()  # 数据库功能测试
    test_database_api()  # 数据库 API 接口测试
    test_pr_details()  # PR详细信息接口测试
    test_pr_detail_info()  # PR详细信息接口测试（新功能）
    test_comment_bot_detection()  # 评论 Bot 识别测试（新功能）
    test_database_query()  # 数据库高级查询测试（新功能）
    test_gitcode_api()  # GitCode API 测试（新功能）

    # 打印汇总
    print_summary()

if __name__ == "__main__":
    main()
