#!/usr/bin/env bash
# 方案 A：将本地 main 推送到远程新分支 v3-intelligence（不覆盖 main）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "错误：当前目录不是 git 仓库"
  exit 1
fi

REMOTE="${GIT_REMOTE:-git@github.com:Czou-hahaha/wechat_auto_pipeline_project.git}"
git remote get-url origin >/dev/null 2>&1 || git remote add origin "$REMOTE"
git remote set-url origin "$REMOTE"

echo "→ 推送到 origin/v3-intelligence ..."
git push -u origin main:v3-intelligence

echo ""
echo "完成。在浏览器打开："
echo "  https://github.com/Czou-hahaha/wechat_auto_pipeline_project/tree/v3-intelligence"
echo ""
echo "可选：在 GitHub → Settings → General → Default branch 将默认分支改为 v3-intelligence"
