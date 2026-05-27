"""
服务监控模块
用于诊断服务卡死问题，记录运行状态
支持自动恢复：检测到卡死时优雅退出，由 watchdog 父进程自动重启
"""
import threading
import time
import traceback
import sys
import os
import subprocess
import psutil
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from functools import wraps
import json

logger = logging.getLogger(__name__)


class ServiceMonitor:
    """
    服务监控器
    记录服务运行状态，诊断卡死问题
    """

    def __init__(self, log_file: str = "monitor.log", heartbeat_interval: int = 10,
                 auto_recovery: bool = False):
        """
        初始化监控器
        :param log_file: 监控日志文件
        :param heartbeat_interval: 心跳间隔（秒）
        :param auto_recovery: 是否启用自动恢复（检测到卡死时自动退出，由 watchdog 重启）
        """
        self.log_file = log_file
        self.heartbeat_interval = heartbeat_interval
        self.auto_recovery = auto_recovery
        self.is_running = False
        self.monitor_thread = None
        self.lock = threading.Lock()

        # 请求追踪
        self.active_requests: Dict[str, Dict[str, Any]] = {}
        self.request_timeout = 60  # 请求超时阈值（秒）

        # 状态记录
        self.last_heartbeat = None
        self.heartbeat_missed = 0
        self.max_heartbeat_miss = 3  # 最大心跳丢失次数

        # 自动恢复状态
        self.recovery_count = 0
        self.last_recovery_time = None

        # 内存监控
        self.memory_threshold = 500 * 1024 * 1024  # 500MB 内存阈值

        # 线程监控
        self.thread_count_history: List[int] = []

        logger.info(f"服务监控器初始化，心跳间隔: {heartbeat_interval}秒，自动恢复: {auto_recovery}")

    def start(self):
        """启动监控"""
        if self.is_running:
            return

        self.is_running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("服务监控已启动")

    def stop(self):
        """停止监控"""
        self.is_running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("服务监控已停止")

    def _monitor_loop(self):
        """监控主循环"""
        while self.is_running:
            try:
                self._check_heartbeat()
                self._check_requests()
                self._check_memory()
                self._check_threads()
                self._write_heartbeat()
                time.sleep(self.heartbeat_interval)
            except Exception as e:
                logger.error(f"监控循环异常: {e}")
                self._log_diagnostic("monitor_error", {"error": str(e), "traceback": traceback.format_exc()})

    def _write_heartbeat(self):
        """写入心跳"""
        self.last_heartbeat = datetime.now()
        self.heartbeat_missed = 0

        status = {
            "type": "heartbeat",
            "timestamp": self.last_heartbeat.isoformat(),
            "active_requests": len(self.active_requests),
            "thread_count": threading.active_count(),
            "memory_mb": psutil.Process().memory_info().rss / 1024 / 1024
        }
        self._append_log(status)

    def _check_heartbeat(self):
        """检查心跳"""
        if self.last_heartbeat is None:
            return

        elapsed = (datetime.now() - self.last_heartbeat).total_seconds()
        if elapsed > self.heartbeat_interval * 2:
            self.heartbeat_missed += 1
            self._log_diagnostic("heartbeat_missed", {
                "elapsed_seconds": elapsed,
                "missed_count": self.heartbeat_missed
            })

            if self.heartbeat_missed >= self.max_heartbeat_miss:
                self._log_diagnostic("service_stuck", {
                    "message": "服务可能卡死，多次心跳丢失",
                    "missed_count": self.heartbeat_missed
                })
                self._dump_thread_status()

                # 自动恢复：优雅退出当前进程，由 watchdog 父进程重启
                if self.auto_recovery:
                    self._trigger_recovery()

    def _check_requests(self):
        """检查超时请求"""
        current_time = time.time()
        timeout_requests = []

        with self.lock:
            for req_id, req_info in list(self.active_requests.items()):
                elapsed = current_time - req_info.get("start_time", 0)
                if elapsed > self.request_timeout:
                    timeout_requests.append({
                        "request_id": req_id,
                        "elapsed": elapsed,
                        "endpoint": req_info.get("endpoint"),
                        "params": req_info.get("params"),
                        "stack": req_info.get("stack")
                    })

        if timeout_requests:
            self._log_diagnostic("timeout_requests", {
                "count": len(timeout_requests),
                "requests": timeout_requests
            })

    def _check_memory(self):
        """检查内存"""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024

            if memory_info.rss > self.memory_threshold:
                self._log_diagnostic("high_memory", {
                    "memory_mb": memory_mb,
                    "threshold_mb": self.memory_threshold / 1024 / 1024,
                    "memory_percent": process.memory_percent()
                })

            # 内存增长过快检测
            gc_objects = len(gc.get_objects()) if 'gc' in dir() else 0
            if gc_objects > 100000:
                self._log_diagnostic("high_gc_objects", {
                    "gc_objects": gc_objects
                })
        except Exception as e:
            logger.error(f"内存检查异常: {e}")

    def _check_threads(self):
        """检查线程状态"""
        thread_count = threading.active_count()
        self.thread_count_history.append(thread_count)

        # 保留最近 10 次记录
        if len(self.thread_count_history) > 10:
            self.thread_count_history.pop(0)

        # 线程数异常增长
        if len(self.thread_count_history) >= 5:
            avg_count = sum(self.thread_count_history[-5:]) / 5
            if thread_count > avg_count * 2 and thread_count > 20:
                self._log_diagnostic("thread_spike", {
                    "current_count": thread_count,
                    "average_count": avg_count
                })
                self._dump_thread_status()

    def _dump_thread_status(self):
        """导出所有线程状态"""
        threads_info = []
        for thread in threading.enumerate():
            thread_info = {
                "name": thread.name,
                "ident": thread.ident,
                "daemon": thread.daemon,
                "is_alive": thread.is_alive()
            }

            # 尝试获取线程堆栈
            try:
                frame = sys._current_frames().get(thread.ident)
                if frame:
                    stack = traceback.format_stack(frame)
                    thread_info["stack"] = "".join(stack)
            except Exception:
                pass

            threads_info.append(thread_info)

        self._log_diagnostic("thread_dump", {
            "thread_count": len(threads_info),
            "threads": threads_info
        })

    def track_request(self, endpoint: str, params: Dict = None) -> str:
        """
        追踪请求开始
        :param endpoint: 端点名称
        :param params: 请求参数
        :return: 请求ID
        """
        import uuid
        req_id = str(uuid.uuid4())[:8]

        with self.lock:
            self.active_requests[req_id] = {
                "endpoint": endpoint,
                "params": params,
                "start_time": time.time(),
                "stack": traceback.format_stack(limit=5)
            }

        return req_id

    def end_request(self, req_id: str):
        """
        结束请求追踪
        :param req_id: 请求ID
        """
        with self.lock:
            if req_id in self.active_requests:
                del self.active_requests[req_id]

    def _log_diagnostic(self, diag_type: str, data: Dict):
        """记录诊断信息"""
        log_entry = {
            "type": "diagnostic",
            "diag_type": diag_type,
            "timestamp": datetime.now().isoformat(),
            "data": data
        }
        self._append_log(log_entry)
        logger.warning(f"诊断: {diag_type} - {json.dumps(data, ensure_ascii=False)[:200]}")

    def _append_log(self, entry: Dict):
        """追加日志"""
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"写入监控日志失败: {e}")

    def get_status(self) -> Dict[str, Any]:
        """获取监控状态"""
        process = psutil.Process()
        return {
            "is_running": self.is_running,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "active_requests": len(self.active_requests),
            "thread_count": threading.active_count(),
            "memory_mb": process.memory_info().rss / 1024 / 1024,
            "cpu_percent": process.cpu_percent(),
            "heartbeat_missed": self.heartbeat_missed,
            "auto_recovery": self.auto_recovery,
            "recovery_count": self.recovery_count,
            "last_recovery_time": self.last_recovery_time.isoformat() if self.last_recovery_time else None,
        }

    def _trigger_recovery(self):
        """触发自动恢复：优雅退出当前进程，由 watchdog 重启"""
        self.recovery_count += 1
        self.last_recovery_time = datetime.now()

        self._log_diagnostic("auto_recovery_triggered", {
            "message": "检测到服务卡死，触发自动恢复",
            "recovery_count": self.recovery_count,
            "action": "进程将以 exit code 42 退出，watchdog 将自动重启",
            "pid": os.getpid(),
        })
        logger.critical(
            f"自动恢复触发 (第 {self.recovery_count} 次)：服务卡死，进程 {os.getpid()} 即将退出"
        )

        # 确保日志已刷盘
        for handler in logging.root.handlers:
            try:
                handler.flush()
            except Exception:
                pass

        # 使用 exit code 42 通知 watchdog 这是自动恢复退出
        os._exit(42)


def timeout_guard(timeout_seconds: int = 30):
    """
    请求超时守护装饰器
    :param timeout_seconds: 超时时间
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            import signal

            def timeout_handler(signum, frame):
                raise TimeoutError(f"请求超时: {func.__name__} 超过 {timeout_seconds} 秒")

            # 仅在 Unix 系统上使用信号
            if hasattr(signal, 'SIGALRM'):
                old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(timeout_seconds)
                try:
                    result = func(*args, **kwargs)
                finally:
                    signal.alarm(0)
                    signal.signal(signal.SIGALRM, old_handler)
                return result
            else:
                return func(*args, **kwargs)

        return wrapper
    return decorator


class ExceptionHook:
    """
    全局异常钩子
    捕获未处理异常并记录
    """

    def __init__(self, monitor: ServiceMonitor):
        self.monitor = monitor
        self.original_excepthook = sys.excepthook

    def __call__(self, exc_type, exc_value, exc_traceback):
        """异常处理"""
        # 记录异常详情
        error_info = {
            "type": "uncaught_exception",
            "timestamp": datetime.now().isoformat(),
            "exception_type": str(exc_type),
            "exception_value": str(exc_value),
            "traceback": "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        }

        self.monitor._append_log(error_info)
        logger.critical(f"未捕获异常: {exc_type}: {exc_value}")

        # 调用原始钩子
        self.original_excepthook(exc_type, exc_value, exc_traceback)

    def install(self):
        """安装异常钩子"""
        sys.excepthook = self
        logger.info("全局异常钩子已安装")


# 全局监控实例
_monitor_instance: Optional[ServiceMonitor] = None


def get_monitor() -> ServiceMonitor:
    """获取全局监控实例"""
    global _monitor_instance
    if _monitor_instance is None:
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "monitor.log")
        _monitor_instance = ServiceMonitor(log_file=log_file, auto_recovery=False)
    return _monitor_instance


def start_monitoring(auto_recovery: bool = False):
    """启动监控
    :param auto_recovery: 是否启用自动恢复（检测到卡死时自动退出，由 watchdog 重启）
    """
    global _monitor_instance

    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "monitor.log")
    _monitor_instance = ServiceMonitor(log_file=log_file, auto_recovery=auto_recovery)
    _monitor_instance.start()

    # 安装异常钩子
    exception_hook = ExceptionHook(_monitor_instance)
    exception_hook.install()

    if auto_recovery:
        logger.info("自动恢复已启用（watchdog 模式）")

    return _monitor_instance


def stop_monitoring():
    """停止监控"""
    global _monitor_instance
    if _monitor_instance:
        _monitor_instance.stop()


# ====================
# Watchdog 进程管理器
# ====================

# 自动恢复退出码（子进程用此码退出表示需要重启）
RECOVERY_EXIT_CODE = 42


class ServiceWatchdog:
    """
    服务看门狗 — 以子进程方式运行服务，监控其存活状态并自动重启

    使用方式：
        python -m app.core.monitor --watchdog

    工作原理：
        1. 以 subprocess 启动 uvicorn 服务进程
        2. 监控子进程退出码：
           - exit code 42 → 服务自检卡死，自动重启（带退避）
           - exit code 0  → 正常退出，不重启
           - 其他 exit code → 异常退出，自动重启（带退避）
        3. 通过 HTTP 心跳检测子进程是否真正可响应
        4. 连续重启失败超过阈值后停止尝试
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 1234,
                 max_restarts: int = 10, restart_cooldown: int = 5,
                 health_check_url: str = None):
        self.host = host
        self.port = port
        self.max_restarts = max_restarts
        self.restart_cooldown = restart_cooldown  # 重启冷却时间（秒），每次翻倍
        self.health_check_url = health_check_url or f"http://{host}:{port}/api/health"
        self.process = None
        self.restart_count = 0
        self.start_time = None

    def _build_cmd(self):
        """构建启动命令"""
        return [
            sys.executable, "-m", "app.main",
        ]

    def _start_process(self):
        """启动服务子进程"""
        env = os.environ.copy()
        env["HOST"] = self.host
        env["PORT"] = str(self.port)
        env["WATCHDOG_MODE"] = "1"  # 告知子进程在 watchdog 模式下运行

        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.process = subprocess.Popen(
            self._build_cmd(),
            cwd=backend_dir,
            env=env,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        self.start_time = datetime.now()
        logger.info(f"服务进程已启动 (PID: {self.process.pid})")

    def _health_check(self, timeout: int = 3) -> bool:
        """HTTP 健康检查"""
        try:
            import urllib.request
            req = urllib.request.Request(self.health_check_url, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _wait_for_healthy(self, max_wait: int = 30) -> bool:
        """等待服务变为健康状态"""
        start = time.time()
        while time.time() - start < max_wait:
            if self._health_check():
                return True
            time.sleep(1)
        return False

    def run(self):
        """watchdog 主循环"""
        logger.info(f"Watchdog 启动 — 目标服务 {self.host}:{self.port}")
        logger.info(f"配置: 最大重启次数={self.max_restarts}, 冷却时间={self.restart_cooldown}s")

        while self.restart_count <= self.max_restarts:
            self._start_process()

            # 等待服务启动完成
            healthy = self._wait_for_healthy(max_wait=30)
            if healthy:
                logger.info(f"服务启动成功 (PID: {self.process.pid})")
                if self.restart_count > 0:
                    logger.info(f"这是第 {self.restart_count} 次自动恢复")
            else:
                logger.warning(f"服务启动后未通过健康检查 (PID: {self.process.pid})，继续监控")

            # 等待子进程退出
            exit_code = self.process.wait()
            uptime = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0

            logger.warning(f"服务进程退出 (PID: {self.process.pid}, exit code: {exit_code}, 运行: {uptime:.0f}s)")

            if exit_code == 0:
                logger.info("服务正常退出，不重启")
                return

            # 异常退出或恢复退出 → 计划重启
            self.restart_count += 1
            if self.restart_count > self.max_restarts:
                logger.critical(f"已达到最大重启次数 ({self.max_restarts})，停止重启")
                return

            # 指数退避：冷却时间随重启次数翻倍，上限 60 秒
            cooldown = min(self.restart_cooldown * (2 ** (self.restart_count - 1)), 60)
            reason = "服务卡死（自动恢复）" if exit_code == RECOVERY_EXIT_CODE else f"异常退出 (code {exit_code})"
            logger.info(f"原因: {reason}，{cooldown}s 后重启 (第 {self.restart_count}/{self.max_restarts} 次)")
            time.sleep(cooldown)

        logger.critical("Watchdog 退出：超过最大重启次数")


def run_watchdog():
    """以 watchdog 模式启动服务"""
    import subprocess

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "1234"))

    watchdog = ServiceWatchdog(host=host, port=port)
    try:
        watchdog.run()
    except KeyboardInterrupt:
        logger.info("Watchdog 收到中断信号")
        if watchdog.process and watchdog.process.poll() is None:
            watchdog.process.terminate()
            watchdog.process.wait(timeout=10)
        logger.info("Watchdog 已停止")