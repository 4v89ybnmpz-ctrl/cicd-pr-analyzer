# 待开发需求

## 1. 细粒度子步骤进度感知

**场景**：ops-registry-invoke 等含 `sub_steps` 的插件（4 大阶段 + 28 子步骤），运行时只有顶层 phase 变色。

**已完成**：
- [x] step prompt 追加 SUBSTEP 标记指令（drive.py 行 315-318）
- [x] event loop 检测 Bash 输出中的 [SUBSTEP:xxx] 并推送 SSE 事件
- [x] 前端 SSE 监听 sub_step_progress，存入 session slice

**待完成**：
- [ ] PluginArchGraph layoutHierarchical 接收 sub_step_progress，子步骤节点运行时变色（蓝脉冲/绿完成）
