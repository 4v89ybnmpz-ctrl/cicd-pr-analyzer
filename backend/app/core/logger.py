"""
日志配置模块
配置应用日志系统，添加服务监控日志输出功能
"""
import logging
import sys
import traceback
from pathlib import Path
from datetime import datetime
import os
import json


def setup_logging(log_file: str = None, log_level: int = None):
    """
    设置日志系统
    :param log_file: 日志文件名（可选，从配置读取）
    :param log_level: 日志级别（可选，从配置读取）
    :return: logger 实例
    """
    # 从配置文件读取日志设置
    config_path = Path(__file__).parent.parent.parent / "config.json"
    log_dir = Path(__file__).parent.parent.parent / "logs"

    # 默认值
    _log_file = "server.log"
    _log_level = logging.INFO

    # 从配置文件读取
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logging_config = config.get("logging", {})
                _log_file = logging_config.get("log_file", "server.log")
                _log_dir = logging_config.get("log_dir", "logs")
                log_dir = Path(__file__).parent.parent.parent / _log_dir

                level_str = logging_config.get("log_level", "INFO")
                _log_level = getattr(logging, level_str.upper(), logging.INFO)
        except Exception:
            pass

    # 使用传入参数覆盖
    if log_file:
        _log_file = log_file
    if log_level:
        _log_level = log_level

    # 确保日志目录存在
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / _log_file

    # 创建日志格式器
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 创建详细的错误格式器
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 创建根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(_log_level)

    # 清除现有的处理器
    root_logger.handlers.clear()

    # 添加文件处理器（使用详细格式）
    file_handler = logging.FileHandler(log_path, encoding='utf-8')
    file_handler.setLevel(_log_level)
    file_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(file_handler)

    # 添加控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(_log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 添加异常处理器
    def handle_exception(exc_type, exc_value, exc_traceback):
        """全局异常处理器"""
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        root_logger.error(
            "未捕获的异常",
            exc_info=(exc_type, exc_value, exc_traceback)
        )

    sys.excepthook = handle_exception

    # 记录日志系统启动
    root_logger.info(f"日志系统初始化完成，日志文件: {log_path}")
    root_logger.info(f"日志级别: {logging.getLevelName(_log_level)}")

    return root_logger


def log_exception(logger: logging.Logger, message: str = "发生异常"):
    """
    记录异常详情到日志
    :param logger: logger 实例
    :param message: 错误消息
    """
    logger.error(message)
    logger.error(f"异常类型: {sys.exc_info()[0].__name__}")
    logger.error(f"异常消息: {str(sys.exc_info()[1])}")
    logger.error(f"异常追踪:\n{traceback.format_exc()}")


# 获取 logger 实例
def get_logger(name: str) -> logging.Logger:
    """
    获取指定名称的 logger
    :param name: logger 名称
    :return: Logger 实例
    """
    return logging.getLogger(name)