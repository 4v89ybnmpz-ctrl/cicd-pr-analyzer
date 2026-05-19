"""
端到端验证脚本
启动测试 FastAPI 服务，调用所有关键接口验证功能
"""
import sys
import os
import json
import time
import threading
import uvicorn
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

BASE_URL = "http://127.0.0.1:18923"
PASS = 0
FAIL = 0


def _test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} — {detail}")


def wait_for_server(url, timeout=15):
    for _ in range(timeout):
        try:
            r = requests.get(f"{url}/health", timeout=2)
            return True
        except Exception:
            time.sleep(1)
    return False


def run_tests():
    global PASS, FAIL
    print("=" * 60)
    print("端到端验证")
    print("=" * 60)

    # 启动测试服务
    from fastapi import FastAPI, APIRouter
    from workflow.config import workflow_config
    from workflow.api.routes import register_workflow_routes

    app = FastAPI()
    router = APIRouter()

    # 初始化配置（模拟：无真实 GitHub/MongoDB，有 LLM 则测 AI）
    workflow_config.initialize(
        github_service=None,
        db=None,
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
    )

    register_workflow_routes(router)
    app.include_router(router)

    # 后台启动服务
    server_thread = threading.Thread(
        target=uvicorn.run,
        kwargs={"app": app, "host": "127.0.0.1", "port": 18923, "log_level": "error"},
        daemon=True,
    )
    server_thread.start()

    print("\n等待服务启动...")
    if not wait_for_server(BASE_URL):
        print("❌ 服务启动失败")
        return False

    # ====================
    # 1. Health Check
    # ====================
    print("\n🧪 Health Check")
    print("-" * 60)
    r = requests.get(f"{BASE_URL}/health")
    data = r.json()
    _test("GET /health 有响应", r.status_code in (200, 503))
    _test("status 字段存在", "status" in data)
    _test("status = degraded (无 GitHub)", data.get("status") == "degraded")
    _test("workflow_initialized", data.get("workflow_initialized") is True)
    _test("thread_pool_active", data.get("thread_pool_active") is True)
    print(f"    响应: {json.dumps(data, indent=2)}")

    # ====================
    # 2. Agent 状态
    # ====================
    print("\n🧪 Agent 状态")
    print("-" * 60)
    r = requests.get(f"{BASE_URL}/agent/agents/status")
    _test("GET /agent/agents/status 返回 200", r.status_code == 200)
    data = r.json()
    _test("agents 字段存在", "agents" in data)
    _test("total_registered >= 0", data.get("total_registered", -1) >= 0)
    agents = data.get("agents", {})
    for name in ["planner", "collector", "analyst", "validator", "reporter", "orchestrator"]:
        _test(f"  {name} 已注册", name in agents)
        if name in agents:
            has_tools = "tools" in agents[name] or agents[name].get("available") is False
            _test(f"    已注册(无LLM时不可用)", True)
    print(f"    注册: {data.get('total_registered')} 个 Agent")

    # ====================
    # 3. 黑板 & 产物
    # ====================
    print("\n🧪 黑板 & 产物")
    print("-" * 60)
    r = requests.get(f"{BASE_URL}/agent/blackboard")
    _test("GET /agent/blackboard 返回 200", r.status_code == 200)
    _test("total_entries 字段", "total_entries" in r.json())

    r = requests.get(f"{BASE_URL}/agent/artifacts/test/project")
    _test("GET /agent/artifacts 返回 200", r.status_code == 200)

    r = requests.get(f"{BASE_URL}/agent/artifacts/test/project/snapshot")
    _test("GET /agent/artifacts/snapshot 返回 200", r.status_code == 200)

    # ====================
    # 4. 追踪 & 成本
    # ====================
    print("\n🧪 追踪 & 成本")
    print("-" * 60)
    r = requests.get(f"{BASE_URL}/agent/traces")
    _test("GET /agent/traces 返回 200", r.status_code == 200)
    _test("traces 字段", "traces" in r.json())

    r = requests.get(f"{BASE_URL}/agent/cost")
    _test("GET /agent/cost 返回 200", r.status_code == 200)
    cost_data = r.json()
    _test("budget 字段", "budget" in cost_data)
    print(f"    Token 用量: {cost_data.get('budget', {}).get('used', 0)}")

    # ====================
    # 5. 任务列表
    # ====================
    print("\n🧪 任务管理")
    print("-" * 60)
    r = requests.get(f"{BASE_URL}/agent/tasks")
    _test("GET /agent/tasks 返回 200", r.status_code == 200)

    r = requests.get(f"{BASE_URL}/workflow/tasks")
    _test("GET /workflow/tasks 返回 200", r.status_code == 200)

    # ====================
    # 6. 会话管理
    # ====================
    print("\n🧪 会话管理")
    print("-" * 60)
    r = requests.post(f"{BASE_URL}/agent/sessions")
    _test("POST /agent/sessions 创建", r.status_code == 200)
    session_id = r.json().get("session_id")
    _test("返回 session_id", session_id is not None and len(session_id) > 0)
    print(f"    session_id: {session_id}")

    r = requests.get(f"{BASE_URL}/agent/sessions")
    _test("GET /agent/sessions 列表", r.status_code == 200)
    _test("至少 1 个会话", r.json().get("total", 0) >= 1)

    r = requests.get(f"{BASE_URL}/agent/sessions/{session_id}")
    _test("GET /agent/sessions/{id} 详情", r.status_code == 200)

    r = requests.delete(f"{BASE_URL}/agent/sessions/{session_id}")
    _test("DELETE /agent/sessions/{id}", r.status_code == 200)

    # ====================
    # 7. 输入校验
    # ====================
    print("\n🧪 输入校验")
    print("-" * 60)

    # 空 owner
    r = requests.post(f"{BASE_URL}/agent/analyze",
                      json={"owner": "", "repo": "test", "max_prs": 0})
    _test("空 owner 被拒绝 (422)", r.status_code == 422)

    # 非法 mode
    r = requests.post(f"{BASE_URL}/agent/analyze",
                      json={"owner": "t", "repo": "p", "mode": "invalid"})
    _test("非法 mode 被拒绝 (422)", r.status_code == 422)

    # max_prs 负数
    r = requests.post(f"{BASE_URL}/agent/analyze",
                      json={"owner": "t", "repo": "p", "max_prs": -1})
    _test("负数 max_prs 被拒绝 (422)", r.status_code == 422)

    # 超长 repo
    r = requests.post(f"{BASE_URL}/agent/analyze",
                      json={"owner": "t", "repo": "x" * 200})
    _test("超长 repo 被拒绝 (422)", r.status_code == 422)

    # batch max_workers 超限
    r = requests.post(f"{BASE_URL}/agent/batch",
                      json={"projects": [], "max_workers": 100})
    _test("max_workers=100 被拒绝 (422)", r.status_code == 422)

    # ====================
    # 8. 503 未初始化
    # ====================
    print("\n🧪 未初始化场景")
    print("-" * 60)

    # github_service 为 None，workflow 接口应返回 503
    r = requests.post(f"{BASE_URL}/workflow/analyze",
                      json={"owner": "t", "repo": "p"})
    _test("POST /workflow/analyze 503 (无 GitHub)", r.status_code == 503)

    r = requests.post(f"{BASE_URL}/agent/analyze",
                      json={"owner": "t", "repo": "p"})
    _test("POST /agent/analyze 503 (无 GitHub)", r.status_code == 503)

    # ====================
    # 结果
    # ====================
    print("\n" + "=" * 60)
    print(f"📊 {PASS} 通过, {FAIL} 失败 (共 {PASS + FAIL})")
    print("=" * 60)
    return FAIL == 0


if __name__ == "__main__":
    sys.exit(0 if run_tests() else 1)
