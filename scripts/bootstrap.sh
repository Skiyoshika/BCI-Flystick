#!/usr/bin/env bash
# Bootstrap script to clone/update the repo, create a Python virtual environment,
# and install dependencies in one go.
set -euo pipefail

REPO_URL="https://github.com/Skiyoshika/BCI-Flystick.git"
TARGET_DIR="BCI-Flystick"
RECREATE_VENV=false
SKIP_GIT=false

usage() {
  cat <<'USAGE'
用法: bootstrap.sh [选项]

选项:
  --repo <url>        指定要克隆的 Git 仓库地址 (默认: https://github.com/Skiyoshika/BCI-Flystick.git)
  --dir <path>        指定目标目录 (默认: BCI-Flystick)
  --recreate-venv     删除并重新创建 .venv 虚拟环境
  --skip-git          跳过 git clone/pull 步骤，仅在当前目录下准备虚拟环境
  -h, --help          显示本帮助信息

示例:
  bash scripts/bootstrap.sh
  bash scripts/bootstrap.sh --dir ~/workspace/BCI-Flystick
  bash scripts/bootstrap.sh --skip-git --recreate-venv
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO_URL="$2"
      shift 2
      ;;
    --dir)
      TARGET_DIR="$2"
      shift 2
      ;;
    --recreate-venv)
      RECREATE_VENV=true
      shift
      ;;
    --skip-git)
      SKIP_GIT=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "未知参数: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ "$SKIP_GIT" == false ]]; then
  if [[ -d "$TARGET_DIR/.git" ]]; then
    echo "[1/3] 仓库已存在，执行 git pull 更新..."
    git -C "$TARGET_DIR" pull --ff-only
  else
    echo "[1/3] 克隆仓库 $REPO_URL 至 $TARGET_DIR..."
    git clone "$REPO_URL" "$TARGET_DIR"
  fi
else
  if [[ ! -d "$TARGET_DIR" ]]; then
    echo "错误: --skip-git 选项要求目标目录已存在: $TARGET_DIR" >&2
    exit 1
  fi
fi

cd "$TARGET_DIR"

if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo "错误: 未找到 python 或 python3 命令" >&2
  exit 1
fi

if [[ "$RECREATE_VENV" == true ]]; then
  echo "[2/3] 删除已有虚拟环境 .venv..."
  rm -rf .venv
fi

if [[ ! -d .venv ]]; then
  echo "[2/3] 创建 Python 虚拟环境 (.venv)..."
  "$PYTHON" -m venv .venv
else
  echo "[2/3] 复用已有虚拟环境 (.venv)"
fi

# shellcheck disable=SC1091
source .venv/bin/activate

pip install --upgrade pip

echo "[3/3] 安装 Python 依赖..."
pip install -r python/requirements.txt

echo "✅ 环境准备完成。"
