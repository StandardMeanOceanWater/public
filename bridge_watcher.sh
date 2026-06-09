#!/usr/bin/env bash
# bridge_watcher.sh — inotify 監視 bridge.jsonl 即時觸發
# 取代 */5 cron，檔案一變動就處理
set -euo pipefail

BRIDGE_DIR="$HOME/.hermes/bridge"
BRIDGE="$BRIDGE_DIR/bridge.jsonl"
SCRIPT="$HOME/.hermes/scripts/bridge_inbox.py"
FLAG="$BRIDGE_DIR/needs_agent.flag"
LOG="$BRIDGE_DIR/watcher.log"

log() {
    echo "[$(date '+%H:%M:%S')] $*" >> "$LOG"
}

log "Watcher 啟動，監視 $BRIDGE"

while true; do
    # 監視 bridge.jsonl 的 modify 事件（寫入）
    inotifywait -q -e modify "$BRIDGE" 2>/dev/null

    # Debounce：短時間內多次寫入只處理一次
    sleep 1

    log "偵測到變動，執行 bridge_inbox.py"
    output=$(python3 "$SCRIPT" 2>&1) || true
    log "$output"

    # 檢查是否需要 agent 處理
    if echo "$output" | grep -q "NEEDS_AGENT"; then
        touch "$FLAG"
        log "⚠️ 標記 needs_agent.flag — 等待 WSL 工作階段處理"
    fi

    # 冷卻：避免 inotify 觸發自己寫入的 modify
    sleep 2
done
