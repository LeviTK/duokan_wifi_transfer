#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$ROOT/dist/logs"
TIMESTAMP="$(date '+%Y%m%d-%H%M%S')"
LOG_FILE="$LOG_DIR/calibre-user-test-$TIMESTAMP.log"
CALIBRE_DEBUG="$(command -v calibre-debug || true)"

if [[ -z "$CALIBRE_DEBUG" && -x /Applications/calibre.app/Contents/MacOS/calibre-debug ]]; then
  CALIBRE_DEBUG=/Applications/calibre.app/Contents/MacOS/calibre-debug
fi

if [[ -z "$CALIBRE_DEBUG" ]]; then
  echo "找不到 calibre-debug。请重新打开终端，或执行："
  echo 'export PATH="/Applications/calibre.app/Contents/MacOS:$PATH"'
  exit 1
fi

if pgrep -x calibre >/dev/null 2>&1; then
  echo "Calibre 已经在运行。请先正常退出，再执行 make user-test。"
  exit 1
fi

mkdir -p "$LOG_DIR"

echo "多看 WiFi 传书用户验收"
echo "1. 手机和电脑连接同一局域网，多看阅读已开启 WiFi 传书。"
echo "2. 在 Calibre 中准备：普通 EPUB、多本 EPUB、较大 EPUB、无 EPUB 格式书籍。"
echo "3. 依次验证：连接成功、错误地址、单本发送、多本发送、格式缺失、手机端打开。"
echo "4. 完成后退出 Calibre；调试日志将保存到：$LOG_FILE"
echo
echo "正在以调试模式启动 Calibre……"

"$CALIBRE_DEBUG" -g 2>&1 | tee "$LOG_FILE"
