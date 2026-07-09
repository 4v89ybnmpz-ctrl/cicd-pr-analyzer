#!/bin/bash
# ------------------------------------------------------------------
# CANN Toolkit 安装脚本（在 Docker build 时执行）
# 用法: install_cann.sh <CANN_PACKAGE> <ASCEND_BASE>
#   CANN_PACKAGE 为空 → 跳过安装，只打印提示
#   CANN_PACKAGE 为 .run 文件路径 → 直接安装
#   CANN_PACKAGE 为 URL → 下载后安装
# ------------------------------------------------------------------
set -eu

CANN_PACKAGE="${1:-}"
ASCEND_BASE="${2:-/usr/local/Ascend}"

if [ -z "$CANN_PACKAGE" ]; then
    echo "========================================"
    echo "⚠ CANN_PACKAGE 未指定，跳过 CANN Toolkit 安装"
    echo "  后续请将宿主机 CANN 目录挂载到容器内，如:"
    echo "  docker run -v /usr/local/Ascend:$ASCEND_BASE ..."
    echo "========================================"
    mkdir -p "$ASCEND_BASE"
    exit 0
fi

echo "========================================"
echo "安装 CANN Toolkit"
echo "源:  $CANN_PACKAGE"
echo "目标: $ASCEND_BASE"
echo "========================================"

mkdir -p "$ASCEND_BASE"

# 转换为本地路径
INSTALLER=""
trap 'rm -f /tmp/cann_installer.run' EXIT

if echo "$CANN_PACKAGE" | grep -qE '^https?://'; then
    echo "→ 下载: $CANN_PACKAGE"
    curl -L --retry 3 --retry-delay 10 -o /tmp/cann_installer.run "$CANN_PACKAGE"
    INSTALLER=/tmp/cann_installer.run
elif [ -f "$CANN_PACKAGE" ]; then
    INSTALLER="$CANN_PACKAGE"
else
    echo "❌ 无法访问 CANN_PACKAGE: $CANN_PACKAGE"
    exit 1
fi

echo "→ 开始安装（log: /tmp/cann_install.log）..."
chmod +x "$INSTALLER"
"$INSTALLER" --install --install-path="$ASCEND_BASE" \
    --quiet 2>&1 | tee /tmp/cann_install.log

echo ""
echo "→ 安装完成，校验..."
AS_TOOLKIT=$(find "$ASCEND_BASE" -maxdepth 2 -name 'set_env.sh' -path '*/ascend-toolkit/*' 2>/dev/null | head -1)
if [ -n "$AS_TOOLKIT" ]; then
    TOOLKIT_DIR=$(dirname "$AS_TOOLKIT")
    echo "✅ CANN Toolkit: $TOOLKIT_DIR"
else
    # 尝试建立 latest 软链
    TOOLKIT=$(find "$ASCEND_BASE" -maxdepth 2 -name 'set_env.sh' 2>/dev/null | head -1)
    if [ -n "$TOOLKIT" ]; then
        TOOLKIT_DIR=$(dirname "$TOOLKIT")
        ln -sf "$TOOLKIT_DIR" "$ASCEND_BASE/ascend-toolkit/latest"
        echo "✅ CANN Toolkit: $TOOLKIT_DIR → latest"
    else
        echo "❌ 安装后未找到 set_env.sh，请检查 CANN 包"
        find "$ASCEND_BASE" -maxdepth 3 -name '*.sh' | head -20
        exit 1
    fi
fi

echo "========================================"
echo "CANN Toolkit 安装完成"
echo "========================================"
