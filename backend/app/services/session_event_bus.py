"""
SessionEventBus — Per-session 实时事件广播

仿真执行与 SSE 连接解耦的核心组件：
  - 后台执行 Task 是事件的生产者（唯一），调用 publish()
  - SSE 端点是事件的订阅者（可多个，如多标签页/重连），调用 subscribe() 拿到自己的 Queue

设计要点：
  - 不维护完整事件历史。DB 是真相之源，SSE 重连时由 stream_session 先发 session_snapshot
    （DB 全量快照）补历史，再订阅本 bus 的实时增量。
  - publish 非阻塞（put_nowait），慢消费者不会反压阻塞整个仿真；Queue 满则丢最旧一条
    （实时性优先，历史以 DB 为准）。
  - finished 标志：后台 Task 结束后置位，订阅者据此知道"实时事件已排空，可以退出"。
"""
import asyncio
import logging

logger = logging.getLogger(__name__)

_QUEUE_MAX = 2000  # 每个订阅者 Queue 上限


class SessionEventBus:
    """Per-session 事件广播：多订阅者 Queue。"""

    def __init__(self):
        self._subscribers: list[asyncio.Queue] = []
        self._finished: bool = False

    async def subscribe(self) -> "asyncio.Queue":
        """订阅，返回一个专属 Queue。订阅者从 Queue 拉实时事件。"""
        q: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAX)
        self._subscribers.append(q)
        return q

    async def unsubscribe(self, q: "asyncio.Queue"):
        """取消订阅（SSE 断开时调用，不影响后台 Task/进程）。"""
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    def publish(self, ev: dict):
        """非阻塞广播到所有订阅者。Queue 满则丢最旧一条再放。"""
        for q in list(self._subscribers):
            try:
                q.put_nowait(ev)
            except asyncio.QueueFull:
                # 满了：丢最旧一条，尝试放新的（保实时）
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    q.put_nowait(ev)
                except asyncio.QueueFull:
                    pass  # 实在放不下，丢弃（DB 仍有）

    def mark_finished(self):
        """后台 Task 结束后调用。订阅者据此退出循环。"""
        self._finished = True
        # 给所有订阅者推一个哨兵事件，唤醒可能在 wait_for(q.get()) 的协程
        sentinel = {"event": "_eof", "data": {}}
        for q in list(self._subscribers):
            try:
                q.put_nowait(sentinel)
            except asyncio.QueueFull:
                pass

    @property
    def finished(self) -> bool:
        return self._finished

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
