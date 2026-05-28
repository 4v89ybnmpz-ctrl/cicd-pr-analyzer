"""
WebSocket PTY 终端路由
在浏览器中提供交互式终端，用于启动 AI 编程工具测试 Skills
"""
import asyncio
import fcntl
import os
import struct
import termios
import pty as pty_module
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)


def register_terminal_routes(router: APIRouter):
    """注册终端 WebSocket 路由"""

    @router.websocket("/ws/terminal")
    async def terminal_websocket(ws: WebSocket):
        """WebSocket PTY 终端：浏览器 <-> PTY 双向转发"""
        await ws.accept()

        master_fd = None
        proc = None

        try:
            master_fd, slave_fd = pty_module.openpty()

            # 初始终端大小
            winsize = struct.pack("HHHH", 24, 80, 0, 0)
            fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)

            shell = os.environ.get("SHELL", "/bin/zsh")
            proc = await asyncio.create_subprocess_exec(
                shell,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                start_new_session=True,
                env={
                    **os.environ,
                    "TERM": "xterm-256color",
                    "COLUMNS": "80",
                    "LINES": "24",
                },
            )
            os.close(slave_fd)
            logger.info(f"终端会话启动: PID={proc.pid}, shell={shell}")

            loop = asyncio.get_event_loop()
            alive = True

            # PTY 输出 → WebSocket（用 run_in_executor 避免阻塞事件循环）
            async def read_pty():
                nonlocal alive
                try:
                    while alive:
                        data = await loop.run_in_executor(None, lambda: os.read(master_fd, 4096))
                        if not data:
                            break
                        if ws.client_state == WebSocketState.CONNECTED:
                            await ws.send_bytes(data)
                except (OSError, Exception):
                    pass
                finally:
                    alive = False

            # WebSocket 输入 → PTY
            async def write_pty():
                nonlocal alive
                try:
                    while alive:
                        try:
                            message = await ws.receive()
                        except Exception:
                            break

                        if not alive:
                            break

                        # 处理文本消息
                        if message.get("type") == "websocket.disconnect":
                            break

                        text = message.get("text")
                        if text:
                            # resize 指令
                            if text.startswith("resize:"):
                                try:
                                    _, cols, rows = text.split(":")
                                    ws_size = struct.pack("HHHH", int(rows), int(cols), 0, 0)
                                    fcntl.ioctl(master_fd, termios.TIOCSWINSZ, ws_size)
                                except Exception:
                                    pass
                            else:
                                os.write(master_fd, text.encode("utf-8"))
                            continue

                        # 处理二进制消息
                        data = message.get("bytes")
                        if data:
                            os.write(master_fd, data)

                except (OSError, Exception):
                    pass
                finally:
                    alive = False

            await asyncio.gather(read_pty(), write_pty())

        except WebSocketDisconnect:
            logger.info("终端 WebSocket 断开")
        except Exception as e:
            logger.error(f"终端会话异常: {e}")
        finally:
            if proc and proc.returncode is None:
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=3)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            if master_fd is not None:
                try:
                    os.close(master_fd)
                except Exception:
                    pass
            logger.info("终端会话已清理")
