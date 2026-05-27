"""
FastAPI 主应用入口
启动 GitHub PR API 服务

支持 watchdog 模式:
    python main.py --watchdog
    以看门狗方式运行，服务卡死时自动重启
"""
import sys
import os

# 添加backend目录到路径，以便导入app模块
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend_dir)

if __name__ == "__main__":
    if "--watchdog" in sys.argv:
        from app.core.monitor import run_watchdog
        run_watchdog()
    else:
        from app.main import main
        main()
