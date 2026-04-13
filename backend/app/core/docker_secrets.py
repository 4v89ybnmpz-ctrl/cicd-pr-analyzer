"""
Docker Secrets 辅助模块
用于从Docker Secrets读取敏感信息
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def read_docker_secret(secret_name: str) -> Optional[str]:
    """
    从Docker Secrets读取密码
    :param secret_name: Secret名称
    :return: Secret内容，如果不存在返回None
    """
    # Docker Secrets默认路径
    secret_path = f"/run/secrets/{secret_name}"
    
    if os.path.exists(secret_path):
        try:
            with open(secret_path, 'r') as f:
                secret_value = f.read().strip()
                logger.info(f"从Docker Secret读取密码成功: {secret_name}")
                return secret_value
        except Exception as e:
            logger.error(f"读取Docker Secret失败: {e}")
            return None
    
    logger.debug(f"Docker Secret不存在: {secret_path}")
    return None


def get_password_from_env_or_secret(env_var: str = "MONGODB_ROOT_PASSWORD", 
                                    secret_name: str = "mongodb_root_password") -> Optional[str]:
    """
    从环境变量或Docker Secrets获取密码
    优先级：Docker Secrets > 环境变量
    :param env_var: 环境变量名
    :param secret_name: Secret名称
    :return: 密码，如果都不存在返回None
    """
    # 1. 尝试从Docker Secrets读取
    password = read_docker_secret(secret_name)
    if password:
        return password
    
    # 2. 尝试从环境变量读取
    password = os.environ.get(env_var)
    if password:
        logger.info(f"从环境变量读取密码成功: {env_var}")
        return password
    
    logger.debug("未找到密码配置，将使用默认值")
    return None


def get_database_password(default_password: str = "admin123") -> str:
    """
    获取数据库密码
    按优先级从多个来源获取密码：
    1. Docker Secrets
    2. 环境变量
    3. 默认值
    :param default_password: 默认密码
    :return: 密码
    """
    password = get_password_from_env_or_secret()
    
    if password:
        return password
    
    logger.info(f"使用默认密码")
    return default_password
