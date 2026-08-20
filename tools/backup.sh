#!/usr/bin/env bash
# 将项目打包备份到 E 盘（Windows 可访问位置），排除可重建物。
# 用法：bash tools/backup.sh
set -euo pipefail

BACKUP_DIR="/mnt/e/ies-backups"
mkdir -p "$BACKUP_DIR"
ARCHIVE="$BACKUP_DIR/ies-$(date +%F).tar.gz"

tar -czf "$ARCHIVE" \
  --exclude="./ies/backend/.venv" \
  --exclude="./ies/frontend/node_modules" \
  --exclude="./ies/frontend/dist" \
  --exclude="./ies/.git" \
  -C "$HOME/projects" ies

echo "备份完成: $ARCHIVE"
ls -lh "$ARCHIVE"
