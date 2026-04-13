"""
测试入口脚本
运行所有测试用例
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入并运行测试
from backend.test import main

if __name__ == "__main__":
    main()
