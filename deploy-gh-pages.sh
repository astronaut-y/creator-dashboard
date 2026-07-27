#!/usr/bin/env bash
# 一键部署宇航员创作工作台到 GitHub Pages
# 用法：./deploy-gh-pages.sh <GitHub用户名> <仓库名>
# 示例：./deploy-gh-pages.sh johndoe creator-dashboard

set -e

USER=${1:-}
REPO=${2:-creator-dashboard}

if [ -z "$USER" ]; then
  echo "❌ 请提供 GitHub 用户名"
  echo "用法：./deploy-gh-pages.sh <GitHub用户名> [仓库名，默认 creator-dashboard]"
  exit 1
fi

REMOTE_URL="https://github.com/$USER/$REPO.git"

echo "🚀 正在部署到 GitHub Pages..."
echo "   用户: $USER"
echo "   仓库: $REPO"
echo "   远程: $REMOTE_URL"

# 进入当前目录
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# 检查是否已有 git 仓库
if [ -d .git ]; then
  echo "📦 已存在 git 仓库，检查远程..."
  git remote get-url origin >/dev/null 2>&1 || git remote add origin "$REMOTE_URL"
else
  echo "📦 初始化 git 仓库..."
  git init
  git remote add origin "$REMOTE_URL"
fi

# 提交代码
git add -A
git commit -m "deploy: update creator dashboard" || true

# 推送到 main 分支
git branch -M main
git push -u origin main

echo ""
echo "✅ 推送完成！"
echo ""
echo "接下来请执行："
echo "1. 打开 https://github.com/$USER/$REPO/settings/pages"
echo "2. Source 选择 Deploy from a branch → main → / (root)"
echo "3. 等待 1-2 分钟"
echo "4. 访问 https://$USER.github.io/$REPO/"
echo ""
echo "💡 提示：把页面加到手机桌面，打开更像原生 App"