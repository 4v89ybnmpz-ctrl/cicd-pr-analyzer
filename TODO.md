# 待开发需求

## 1. 细粒度子步骤进度感知

**场景**：ops-registry-invoke 等含 `sub_steps` 的插件（4 大阶段 + 28 子步骤），评估运行时只有顶层 phase 节点变色，前端看不到具体子步骤的执行进度。

**方案**：
- `PLATFORM_INSTALL_PROMPT` / step prompt 中加一句：每完成一个子步骤前，用 Bash 输出 `[SUBSTEP:1.1 开发准备]` 标记
- `drive.py` 的 event 循环检测 Bash 输出中的 `[SUBSTEP:xxx]`，匹配子步骤列表
- 推送 `sub_step_progress` SSE 事件，分层图对应节点变色

**状态**：待开发
