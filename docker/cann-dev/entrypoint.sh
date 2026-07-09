#!/bin/bash
# ------------------------------------------------------------------
# 容器入口：source CANN 环境 + ascendc-env-setup 环境片段，然后执行 CMD
# ------------------------------------------------------------------
set -e

# 1) source CANN Toolkit set_env.sh（如果存在）
if [ -f /usr/local/Ascend/ascend-toolkit/latest/set_env.sh ]; then
    echo "[entrypoint] source /usr/local/Ascend/ascend-toolkit/latest/set_env.sh"
    source /usr/local/Ascend/ascend-toolkit/latest/set_env.sh
fi

# 2) source 算子库 .env.ascendc.sh（由 ascendc-env-setup/setup_env.sh 生成）
if [ -f /workspace/.env.ascendc.sh ]; then
    echo "[entrypoint] source /workspace/.env.ascendc.sh"
    source /workspace/.env.ascendc.sh
fi

# 3) 激活 Python venv（如果存在）
if [ -f /workspace/.venv/bin/activate ]; then
    echo "[entrypoint] source /workspace/.venv/bin/activate"
    source /workspace/.venv/bin/activate
fi

echo "[entrypoint] 环境就绪"
exec "$@"
