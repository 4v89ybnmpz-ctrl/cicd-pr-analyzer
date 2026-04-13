"""
密码加密模块
使用AES加密算法对敏感信息进行加密存储
"""
import base64
import hashlib
import os
import json
from typing import Optional
import logging

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    ENCRYPTION_AVAILABLE = True
except ImportError:
    ENCRYPTION_AVAILABLE = False

logger = logging.getLogger(__name__)


class PasswordManager:
    """
    密码管理器
    负责密码的加密和解密
    """

    def __init__(self, key_file: str = "encryption_key.json"):
        """
        初始化密码管理器
        :param key_file: 加密密钥文件路径
        """
        if not ENCRYPTION_AVAILABLE:
            logger.warning("cryptography 库未安装，加密功能不可用")
            self.fernet = None
            return

        self.key_file = key_file
        self.fernet = self._load_or_create_key()
        logger.info("密码管理器初始化完成")

    def _load_or_create_key(self) -> Optional[Fernet]:
        """
        加载或创建加密密钥
        :return: Fernet 加密器
        """
        try:
            # 检查密钥文件是否存在
            if os.path.exists(self.key_file):
                with open(self.key_file, 'r', encoding='utf-8') as f:
                    key_data = json.load(f)
                    key = base64.urlsafe_b64decode(key_data['key'].encode('utf-8'))
                    logger.info("从文件加载加密密钥")
            else:
                # 创建新密钥
                key = Fernet.generate_key()
                key_data = {
                    'key': base64.urlsafe_b64encode(key).decode('utf-8'),
                    'created_at': __import__('datetime').datetime.now().isoformat()
                }
                with open(self.key_file, 'w', encoding='utf-8') as f:
                    json.dump(key_data, f, indent=2, ensure_ascii=False)
                # 设置文件权限为只有所有者可读写
                os.chmod(self.key_file, 0o600)
                logger.info("创建新的加密密钥")

            return Fernet(key)

        except Exception as e:
            logger.error(f"加载或创建密钥失败: {e}")
            return None

    def encrypt(self, password: str) -> Optional[str]:
        """
        加密密码
        :param password: 明文密码
        :return: 加密后的密码（Base64编码）
        """
        if self.fernet is None:
            logger.warning("加密功能不可用，返回原始密码")
            return password

        try:
            encrypted_bytes = self.fernet.encrypt(password.encode('utf-8'))
            encrypted_password = base64.urlsafe_b64encode(encrypted_bytes).decode('utf-8')
            logger.info("密码加密成功")
            return encrypted_password
        except Exception as e:
            logger.error(f"密码加密失败: {e}")
            return None

    def decrypt(self, encrypted_password: str) -> Optional[str]:
        """
        解密密码
        :param encrypted_password: 加密的密码（Base64编码）
        :return: 明文密码
        """
        if self.fernet is None:
            logger.warning("加密功能不可用，返回原始密码")
            return encrypted_password

        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_password.encode('utf-8'))
            decrypted_bytes = self.fernet.decrypt(encrypted_bytes)
            password = decrypted_bytes.decode('utf-8')
            logger.info("密码解密成功")
            return password
        except Exception as e:
            logger.error(f"密码解密失败: {e}")
            return None

    def is_encrypted(self, password: str) -> bool:
        """
        检查密码是否已加密
        :param password: 密码字符串
        :return: 是否已加密
        """
        if self.fernet is None:
            return False

        try:
            # 尝试解密，如果能解密成功则认为是加密的
            encrypted_bytes = base64.urlsafe_b64decode(password.encode('utf-8'))
            self.fernet.decrypt(encrypted_bytes)
            return True
        except:
            return False

    def hash_password(self, password: str) -> str:
        """
        生成密码哈希（用于验证，不可逆）
        :param password: 明文密码
        :return: 哈希值
        """
        # 使用SHA256生成哈希
        return hashlib.sha256(password.encode('utf-8')).hexdigest()

    def verify_password(self, password: str, hashed_password: str) -> bool:
        """
        验证密码
        :param password: 明文密码
        :param hashed_password: 哈希值
        :return: 是否匹配
        """
        return self.hash_password(password) == hashed_password


# 全局密码管理器实例
_password_manager = None


def get_password_manager() -> PasswordManager:
    """
    获取全局密码管理器实例
    :return: PasswordManager 实例
    """
    global _password_manager
    if _password_manager is None:
        _password_manager = PasswordManager()
    return _password_manager
