#!/usr/bin/env bash
# IES 一键部署到线上（宝塔/阿里云 120.26.53.206，站点 IES.lightingai.top）
# 流程：本地构建前端 → 打包 → 上传 → 服务器备份旧版/解包/装依赖/重启后端 → 上线前端 → 验证
#
# 前置条件：
#   1. 本机存在部署私钥 ~/.ssh/ies-deploy（可改 IES_KEY 环境变量指定）
#   2. 服务器已安装对应公钥。每次部署完公钥会被移除（不留后门），下次部署前在
#      宝塔面板「终端」粘贴执行（root 下）：
#      mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo '<~/.ssh/ies-deploy.pub 内容>' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys
#
# 用法：bash tools/deploy.sh
# 可覆盖：IES_SERVER（默认 root@120.26.53.206）、IES_KEY（默认 ~/.ssh/ies-deploy）
set -euo pipefail
cd "$(dirname "$0")/.."

SERVER="${IES_SERVER:-root@120.26.53.206}"
KEY="${IES_KEY:-$HOME/.ssh/ies-deploy}"
STAMP=$(date +%Y%m%d%H%M)
PKG="/tmp/ies-deploy-${STAMP}.tar.gz"

echo "== 1/5 本地构建前端 =="
(cd frontend && npm run build)

echo "== 2/5 打包（排除 venv/node_modules/uploads/outputs） =="
tar czf "$PKG" backend/app backend/requirements.txt backend/pytest.ini \
  frontend/src frontend/index.html frontend/package.json frontend/vite.config.js frontend/dist

echo "== 3/5 上传到服务器 =="
scp -q -i "$KEY" "$PKG" "$SERVER:/tmp/$(basename "$PKG")"

echo "== 4/5 服务器更新（备份/解包/装依赖/重启/上线） =="
ssh -o BatchMode=yes -o ConnectTimeout=10 -i "$KEY" "$SERVER" \
  "REMOTE_PKG=/tmp/$(basename "$PKG") STAMP=${STAMP} bash -s" <<'REMOTE'
set -e
cd /www/server/ies
mv backend/app backend/app-old-${STAMP}
tar xzf "$REMOTE_PKG" -C /www/server/ies/
rm -rf frontend/dist && tar xzf "$REMOTE_PKG" -C /www/server/ies/ frontend/dist
chown -R www:www backend/app backend/requirements.txt backend/pytest.ini \
  frontend/src frontend/dist frontend/index.html frontend/package.json frontend/vite.config.js
sudo -u www backend/.venv/bin/pip install -q --disable-pip-version-check \
  -r backend/requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
systemctl restart ies-backend
sleep 3
echo "后端服务: $(systemctl is-active ies-backend)"
cd /www/wwwroot/IES.lightingai.top
mv assets assets-old-${STAMP}
mv index.html index-old-${STAMP}.html
cp -r /www/server/ies/frontend/dist/* .
chown www:www index.html assets
rm -f "$REMOTE_PKG"
REMOTE

echo "== 5/5 线上验证 =="
curl -s --max-time 15 https://ies.lightingai.top/ | grep -o 'assets/index-[^"]*\.js' || echo "首页未返回新资产（请检查）"
curl -s -o /dev/null -w "API 健康检查:%{http_code}\n" --max-time 15 https://ies.lightingai.top/api/health
echo "部署完成。"
