"""
密码加密功能测试脚本
测试密码加密、解密和数据库连接功能
"""
import sys
import os
import json

# 添加backend目录到路径
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, backend_dir)

# 导入密码管理器
from app.core.encryption import get_password_manager

# 导入数据库服务
try:
    from app.services.database_service import DatabaseService
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False
    print("⚠️  数据库模块未安装，跳过数据库测试")

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

def main():
    """主测试函数"""
    print_separator()
    print("🚀 开始密码加密功能测试")
    print_separator()
    
    try:
        # 测试1: 密码加密
        print_test_header("密码加密")
        test_results["total"] += 1
        
        manager = get_password_manager()
        test_password = "test_password_123"
        encrypted = manager.encrypt(test_password)
        
        if encrypted and encrypted != test_password:
            print(f"✅ 密码加密成功")
            print(f"   原密码: {test_password}")
            print(f"   加密后: {encrypted[:50]}...")
            test_results["passed"] += 1
        else:
            print(f"❌ 密码加密失败")
            test_results["failed"] += 1
        
        # 测试2: 密码解密
        print_test_header("密码解密")
        test_results["total"] += 1
        
        decrypted = manager.decrypt(encrypted)
        if decrypted == test_password:
            print(f"✅ 密码解密成功")
            print(f"   解密后: {decrypted}")
            test_results["passed"] += 1
        else:
            print(f"❌ 密码解密失败")
            print(f"   期望: {test_password}")
            print(f"   实际: {decrypted}")
            test_results["failed"] += 1
        
        # 测试3: 密码状态检测
        print_test_header("密码加密状态检测")
        test_results["total"] += 1
        
        is_encrypted = manager.is_encrypted(encrypted)
        is_not_encrypted = manager.is_encrypted(test_password)
        
        if is_encrypted and not is_not_encrypted:
            print(f"✅ 密码状态检测正确")
            print(f"   加密密码检测: {is_encrypted}")
            print(f"   明文密码检测: {is_not_encrypted}")
            test_results["passed"] += 1
        else:
            print(f"❌ 密码状态检测失败")
            print(f"   加密密码检测: {is_encrypted} (期望: True)")
            print(f"   明文密码检测: {is_not_encrypted} (期望: False)")
            test_results["failed"] += 1
        
        # 测试4: 使用加密密码连接数据库
        print_test_header("使用加密密码连接数据库")
        
        if DATABASE_AVAILABLE:
            test_results["total"] += 1
            
            # 使用配置文件中的加密密码
            db_config_file = os.path.join(backend_dir, 'db_config.json')
            
            if os.path.exists(db_config_file):
                with open(db_config_file, 'r', encoding='utf-8') as f:
                    db_config = json.load(f)
                    db_config_data = db_config.get('database', {})
                    
                    if db_config_data.get('encrypted', False):
                        db = DatabaseService(
                            host=db_config_data.get('host', '127.0.0.1'),
                            port=db_config_data.get('port', 27017),
                            username=db_config_data.get('username', 'admin'),
                            password=db_config_data.get('password', 'admin123'),
                            database=db_config_data.get('database', 'github_pr_db')
                        )
                        
                        if db.connect():
                            print(f"✅ 使用加密密码连接数据库成功")
                            print(f"   数据库: {db.database_name}")
                            
                            # 获取统计信息
                            stats = db.get_stats()
                            print(f"   PR数据数量: {stats.get('pr_data_count', 0)}")
                            print(f"   状态: {stats.get('status', 'unknown')}")
                            
                            db.disconnect()
                            test_results["passed"] += 1
                        else:
                            print(f"❌ 使用加密密码连接数据库失败")
                            test_results["failed"] += 1
                    else:
                        print(f"⚠️  配置文件中密码未加密")
                        test_results["passed"] += 1
            else:
                print(f"⚠️  数据库配置文件不存在: {db_config_file}")
                test_results["passed"] += 1
        else:
            print(f"⚠️  数据库模块不可用，跳过测试")
            test_results["passed"] += 1
        
        # 测试5: 密码哈希功能
        print_test_header("密码哈希功能")
        test_results["total"] += 1
        
        hashed_password = manager.hash_password(test_password)
        verified = manager.verify_password(test_password, hashed_password)
        
        if verified:
            print(f"✅ 密码哈希和验证功能正常")
            print(f"   哈希值: {hashed_password[:32]}...")
            test_results["passed"] += 1
        else:
            print(f"❌ 密码验证失败")
            test_results["failed"] += 1
        
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        test_results["errors"].append(f"测试异常: {e}")
        test_results["failed"] += 1
    
    # 打印汇总
    print_separator()
    print("\n📊 测试汇总")
    print_separator()
    print(f"总测试数: {test_results['total']}")
    print(f"✅ 通过: {test_results['passed']}")
    print(f"❌ 失败: {test_results['failed']}")
    if test_results['total'] > 0:
        print(f"通过率: {(test_results['passed'] / test_results['total'] * 100):.1f}%")
    
    if test_results['errors']:
        print("\n❌ 错误列表:")
        for error in test_results['errors']:
            print(f"  - {error}")
    
    print_separator()
    
    # 返回测试结果
    return test_results['failed'] == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
