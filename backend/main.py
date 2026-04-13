"""
FastAPI 主应用入口
启动 GitHub PR API 服务
"""
import sys
import os

# 添加backend目录到路径，以便导入app模块
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend_dir)

from app.main import main

if __name__ == "__main__":
    main()
