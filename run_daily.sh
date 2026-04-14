#!/bin/bash
# 每日生成中国社会情报内参
# 用法：
#   手动运行：bash run_daily.sh
#   加入 crontab（每天早上 8:00）：
#     crontab -e
#     0 8 * * * /bin/bash /Users/wangjiawei/Desktop/China\ A.I./run_daily.sh >> /Users/wangjiawei/Desktop/China\ A.I./logs/cron.log 2>&1

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

LOG_FILE="$LOG_DIR/$(date +%Y-%m-%d).log"

echo "[$(date)] 开始生成..." | tee -a "$LOG_FILE"

python3 "$SCRIPT_DIR/generate.py" 2>&1 | tee -a "$LOG_FILE"
python3 "$SCRIPT_DIR/generate_dprk.py" 2>&1 | tee -a "$LOG_FILE"

echo "[$(date)] 推送到 GitHub..." | tee -a "$LOG_FILE"
cd "$SCRIPT_DIR"
git add docs/
git commit -m "digest: $(date +%Y-%m-%d)" 2>&1 | tee -a "$LOG_FILE"
git push 2>&1 | tee -a "$LOG_FILE"

echo "[$(date)] 完成" | tee -a "$LOG_FILE"
