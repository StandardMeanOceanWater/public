#!/usr/bin/env python3
"""
Exa usage tracker + Telegram reporter.
Usage: python3 exa_usage_check.py [--report] [--reset]

Counts Exa searches from Hermes agent log, calculates cost, sends Telegram report.
"""

import json
import os
import sys
import glob
from datetime import datetime, timezone
from pathlib import Path

# Config
EXA_COST_PER_SEARCH = 0.007  # USD
EXA_TOTAL_CREDIT = 20.00    # USD
USAGE_THRESHOLD = 0.85      # 85%
LOG_DIR = Path.home() / ".hermes" / "logs"

def count_exa_searches_from_log():
    """Count 'Exa search' occurrences in Hermes logs."""
    count = 0
    log_files = sorted(LOG_DIR.glob("*.log"))
    for log_file in log_files:
        try:
            with open(log_file, "r", errors="ignore") as f:
                for line in f:
                    if "Exa search" in line or "exa_search" in line:
                        count += 1
        except Exception:
            pass
    return count

def get_telegram_cfg():
    """Read Telegram config from .env."""
    cfg = {"bot_token": "", "chat_id": ""}
    env_path = Path.home() / ".hermes" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("#"):
                continue
            if line.startswith("NEWSBOY_BOT_TOKEN="):
                cfg["bot_token"] = line.split("=", 1)[1].strip()
            elif line.startswith("NEWSBOY_CHAT_ID="):
                cfg["chat_id"] = line.split("=", 1)[1].strip()
            elif line.startswith("TELEGRAM_BOT_TOKEN="):
                cfg["bot_token"] = line.split("=", 1)[1].strip()
            elif line.startswith("TELEGRAM_ALLOWED_USERS="):
                cfg["chat_id"] = line.split("=", 1)[1].strip()
    return cfg

def send_telegram(message, bot_token, chat_id):
    """Send message via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}}
    try:
        import urllib.request
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read())
    except Exception as e:
        print(f"Telegram send failed: {e}")
        return None

def format_report(searches, cost, remaining, used_pct):
    """Format usage report message."""
    threshold_pct = USAGE_THRESHOLD * 100

    if used_pct >= threshold_pct:
        status = "🔴 警告：已達 85% 門檻！"
    elif used_pct >= 70:
        status = "🟠 注意：已達 70%"
    elif used_pct >= 50:
        status = "🟡 已達 50%"
    else:
        status = "🟢 正常"

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"📊 <b>Exa 用量報告</b> ({now})",
        f"",
        f"狀態：{status}",
        f"",
        f"🔍 總搜尋次數：{searches:,} 次",
        f"💰 已用金額：${cost:.2f} USD",
        f"💵 剩餘金額：${remaining:.2f} USD",
        f"📈 使用率：{used_pct:.1f}%",
        f"",
        f"每次搜尋費用：${EXA_COST_PER_SEARCH}",
        f"總額度：${EXA_TOTAL_CREDIT} USD",
        f"警告門檻：{threshold_pct:.0f}%",
    ]

    if used_pct >= threshold_pct:
        lines.append("")
        lines.append("⚠️ Exa 用量已達 85%，建議切換到 Tavily 或充值")

    return "\n".join(lines)

def main():
    args = sys.argv[1:]

    if "--reset" in args:
        print("Counter reset (log-based, no file to reset).")
        return

    # Count from log
    searches = count_exa_searches_from_log()
    cost = searches * EXA_COST_PER_SEARCH
    remaining = max(0, EXA_TOTAL_CREDIT - cost)
    used_pct = min(100, (cost / EXA_TOTAL_CREDIT) * 100) if EXA_TOTAL_CREDIT > 0 else 0

    if "--report" in args:
        report = format_report(searches, cost, remaining, used_pct)
        # Plain text for terminal
        print(report.replace("<b>", "").replace("</b>", ""))

        # Send to Telegram
        cfg = get_telegram_cfg()
        if cfg["bot_token"] and cfg["chat_id"]:
            result = send_telegram(report, cfg["bot_token"], cfg["chat_id"])
            if result and result.get("ok"):
                print("\n✅ Telegram 通知已發送")
            else:
                print(f"\n❌ Telegram 發送失敗: {result}")
        else:
            print("\n⚠️ Telegram 未設定（找不到 NEWSBOY_BOT_TOKEN 或 NEWSBOY_CHAT_ID）")
    else:
        # Default: show current status
        print(f"Exa Usage: {searches} searches, ${cost:.2f} / ${EXA_TOTAL_CREDIT} ({used_pct:.1f}%)")
        print(f"Remaining: ${remaining:.2f}")
        print(f"Threshold ({USAGE_THRESHOLD*100:.0f}%): ${EXA_TOTAL_CREDIT * USAGE_THRESHOLD:.2f}")

if __name__ == "__main__":
    main()
